# This file is desined to loop though a folder of simular PDF's', pulling all the data into one CSV file.
# first is seperates the page in half loodping over the right and then the left side of the page pulling
# in contest titles, candidates and vots. 

#  pdf_path = "Woolwich Precinct Report.pdf"  

import pdfplumber
import pandas as pd
import re
import logging
from collections import defaultdict
import os

# Set folder path and output CSV
input_folder = "../input"  # change to your folder name
output_csv = "../output/Gloucester_County---06-04-2013_Primary_Election.csv"

# Set up logging
logging.basicConfig(filename='../logs/pdf_extraction_single_column_v4_fixed.log',filemode='w', level=logging.DEBUG, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Paths
pdf_files = [os.path.join(input_folder, f) for f in os.listdir(input_folder) if f.lower().endswith('.pdf')]


# Initialize data structures
data = []
candidate_array = []
meta_data = {}
skip_summary = False
seen_districts = set()


# Regular expressions
header_election_pattern = re.compile(r"^(.*?)\s+(\d{4})\s+Primary Election\s*$|^2013 Primary$")
header_date_pattern = re.compile(r"^(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\s*$|^June 4,$")
header_precinct_pattern = re.compile(r"^Precinct Report\s*$|^Precinct$")
header_county_pattern = re.compile(r"Gloucester")
header_district_pattern = re.compile(r"^(Woolwich\s+(District\s+\d+|Mail-In Ballot|Provisional))$")
contest_pattern = re.compile(r"^(REPB|DEMO|LIB|ACP)\s*-\s*(.*?)\s*$")
registration_pattern = re.compile(r"^(Republican|Democratic|(Non-Partisan))\s+Registration & Turnout$")
candidate_pattern = re.compile(r"^(.*?)\s+(\d+,?\d*)\s+(\d+\.\d{2}%)$")
votes_pattern = re.compile(r"^(Election Day Turnout|Mail-In Ballot Turnout|Provisional Turnout|Cast Votes|Over Votes|Under Votes|Total\.\.\.)\s+(\d+,?\d*)\s+(\d+\.\d{2}%)$")
percent_pattern = re.compile(r"^(\d+\.\d{2}%)$")

summary_line_patterns = [
    r"(?i)Registration & Turnout",
    r"(?i)Election Day Turnout",
    r"(?i)Mail-In Ballot Turnout",
    r"(?i)Provisional Turnout",
    r"(?i)Total.*\d",
    r"\(\s*Final\s*\)",
]

# Function to extract precinct number or type from district name
def extract_precinct(district):
    if not district:
        return "Unknown"
    if "Provisional" in district:
        return "Provisional"
    if "Mail-In Ballot" in district:
        return "Mail-In Ballot"
    match = re.match(r".*(District \d+)", district)
    match2 = re.match(r".* (\d+)", district)
    if match:
        return match.group(1)
    elif match2:
        return match2.group(1)

    return "Unknown"

# New function to help filter valid precinct names
def is_valid_precinct_line(line: str) -> bool:
    # Reject lines that are likely headings or summary data
    reject_keywords = [
        "registration", "turnout", "total", "ballot",
        "provisional", "final", "report", "county"
    ]
    lower = line.lower()
    return (
        bool(line.strip()) and
        not any(word in lower for word in reject_keywords) and
        not line.strip().isdigit()  # skip lines with only numbers
    )



# Function to group words into lines based on y-coordinate
def group_words_into_lines(words):
    lines = defaultdict(list)
    for word in words:
        y = round(word['top'], 1)  # Group by y-coordinate (rounded)
        lines[y].append(word)
    sorted_lines = []
    for y in sorted(lines.keys()):
        sorted_words = sorted(lines[y], key=lambda w: w['x0'])
        line_text = " ".join(word['text'] for word in sorted_words)
        sorted_lines.append(line_text.strip())
        logging.debug(f"Line at y={y}: {line_text} (x0={[w['x0'] for w in sorted_words]})")
    return sorted_lines

# Open the PDF
for pdf_path in pdf_files:
    try:
        with pdfplumber.open(pdf_path) as pdf:
            next_line_is_precinct = False
            current_election = ""
            current_date = ""
            current_county = ""
            current_district = ""
            current_office = ""
            current_party = "N/A"
            header_lines = []
            prev_line = ""

            # Extract municipality from filename
            basename = os.path.basename(pdf_path)
            municipality_match = re.match(r"^(.*?)\s+Precinct Report", basename, re.IGNORECASE)
            municipality = municipality_match.group(1).strip() if municipality_match else "Unknown"
            logging.info(f"Municipality extracted from filename: {municipality}")


            for page_num, page in enumerate(pdf.pages, 1):
                logging.info(f"Processing page {page_num}")
                print(f"Processing page {page_num}...")

                # Extract words with coordinates
                words = page.extract_words()
                if not words:
                    logging.warning(f"No words extracted from page {page_num}")
                    print(f"No words extracted from page {page_num}")
                    continue

                # Log word coordinates for debugging
                logging.debug(f"Page {page_num} words: {[w['text'] + f' (x0={w['x0']}, top={w['top']})' for w in words]}")

                # Separate words into left and right columns
                page_width = page.width
                column_threshold = page_width / 2
                left_column_words = [w for w in words if w['x0'] < column_threshold]
                right_column_words = [w for w in words if w['x0'] >= column_threshold]

                # Convert words to lines
                left_lines = group_words_into_lines(left_column_words)
                right_lines = group_words_into_lines(right_column_words)
                lines = left_lines + right_lines
                logging.debug(f"Page {page_num} lines after column alignment:\n{lines}")
                print(f"Page {page_num} line count: {len(lines)}")

                processed_lines = []
                i = 0
                while i < len(lines):
                    line = lines[i].strip()
                    if not line:
                        i += 1
                        continue

                    # Check if the next line is a percentage
                    if i + 1 < len(lines) and percent_pattern.match(lines[i + 1].strip()):
                        line = f"{line} {lines[i + 1].strip()}"
                        i += 2
                    else:
                        i += 1
                    processed_lines.append(line)

                for line in processed_lines:
                    logging.debug(f"Processing line: {line}")

                    if not line:
                        continue  # skip blank lines

                    if (
                        municipality.lower() in line.lower() and
                        is_valid_precinct_line(line) and
                        not contest_pattern.match(line)  # 🚫 Exclude contest lines
                    ):
                        current_district = line.strip()
                        seen_districts.add(current_district)  # ← track all seen districts
                        logging.info(f"District line matched using municipality '{municipality}': {current_district}")
                        skip_summary = True  # Skip registration data

                        continue

                    # if next_line_is_precinct:
                    #     if is_valid_precinct_line(line):
                    #         current_district = line.strip()
                    #         seen_districts.add(current_district)  # ← track all seen districts
                    #         logging.info(f"District (from next line after county) set to: {current_district}")
                    #         next_line_is_precinct = False
                    #         skip_summary = True
                    #     else:
                    #         logging.debug(f"Rejected as district: {line}")
                    #     continue

                    # Skip footer-like lines
                    if re.match(r"^(June 07, 2013 11:35 AM|Page \d+ of \d+|Election|2013|Report|County)$", line):
                        logging.debug(f"Skipped footer/header fragment: {line}")
                        print(f"Skipped: {line}")
                        continue

                    # Handle multi-line header
                    if not (current_election and current_date and current_county and current_district):
                        header_lines.append(line)

                        # Match election
                        election_match = header_election_pattern.match(line)
                        if election_match:
                            current_election = election_match.group(0) if election_match.group(0) != "2013 Primary" else "Primary Election 2013"
                            logging.info(f"Election matched: {current_election}")
                            print(f"Election matched: {current_election}")
                            continue

                        # Match date
                        date_match = header_date_pattern.match(line)
                        if date_match:
                            current_date = date_match.group(0) if date_match.group(0) != "June 4," else "June 4, 2013"
                            logging.info(f"Date matched: {current_date}")
                            print(f"Date matched: {current_date}")
                            continue

                        # Match county (formerly precinct)
                        county_match = header_county_pattern.match(line)
                        if county_match:
                            current_county = "Gloucester County"
                            next_line_is_precinct = True  # 👈 Set the flag so next line becomes the precinct
                            logging.info(f"County matched: {current_county}. Next line will be set as district.")
                            print(f"County matched: {current_county}")
                            continue

                    if skip_summary and any(re.search(pat, line) for pat in summary_line_patterns):
                        logging.debug(f"Skipping summary table line: {line}")
                        continue

                    # # Skip summary tables after district change
                    # if skip_summary:
                    #     votes_match = votes_pattern.match(line)
                    #     if votes_match:
                    #         logging.debug(f"Skipping summary table line: {line}")
                    #         print(f"Skipped summary: {line}")
                    #         continue
                    #     # End summary skipping when a contest is detected
                    #     contest_match = contest_pattern.match(line)
                    #     if contest_match:
                    #         skip_summary = False
                    #     else:
                    #         logging.debug(f"Skipping potential summary line: {line}")
                    #         print(f"Skipped potential summary: {line}")
                    #         continue

                    # Match registration headers
                    registration_match = registration_pattern.match(line)
                    if registration_match:
                        logging.info(f"Registration section: {line}")
                        print(f"Registration section: {line}")
                        continue

                    # Match contest
                    contest_match = contest_pattern.match(line)
                    if contest_match:
                        # Save any pending candidates
                        if candidate_array:
                            for candidate_row in candidate_array:
                                candidate_row["Cast Votes"] = meta_data.get(current_office, {}).get(current_party, {}).get("Cast Votes", "0")
                                candidate_row["Cast %"] = meta_data.get(current_office, {}).get(current_party, {}).get("Cast Votes %", "0.00%")
                                candidate_row["Over Votes"] = meta_data.get(current_office, {}).get(current_party, {}).get("Over Votes", "0")
                                candidate_row["Over %"] = meta_data.get(current_office, {}).get(current_party, {}).get("Over Votes %", "0.00%")
                                candidate_row["Under Votes"] = meta_data.get(current_office, {}).get(current_party, {}).get("Under Votes", "0")
                                candidate_row["Under %"] = meta_data.get(current_office, {}).get(current_party, {}).get("Under Votes %", "0.00%")
                                data.append(candidate_row)
                            candidate_array.clear()
                            logging.info(f"Added {len(data)} candidates to data for {current_office}")

                        current_party = contest_match.group(1)
                        current_office = contest_match.group(2).strip()
                        meta_data[current_office] = meta_data.get(current_office, {})
                        logging.info(f"Contest matched: Office={current_office}, Party={current_party}")
                        print(f"Contest matched: {current_office}")
                        continue

                    # Match candidate
                    candidate_match = candidate_pattern.match(line)
                    if candidate_match:
                        candidate_name = candidate_match.group(1).strip()
                        votes = candidate_match.group(2).replace(",", "")
                        percent = candidate_match.group(3)
                        logging.info(f"Candidate matched: {candidate_name}, Votes={votes}, Percent={percent}")
                        print(f"Candidate matched: {candidate_name}")

                        candidate_array.append({
                            "Election": current_election or "Primary Election 2013",
                            "Date": current_date or "June 4, 2013",
                            "County": current_county or "Gloucester County",
                            "District": current_district or "Unknown",
                            "Precinct": extract_precinct(current_district),
                            "Office": current_office or "Unknown",
                            "Party": current_party,
                            "Candidate": candidate_name,
                            "Election Day Votes": votes,
                            "Election Day %": percent
                        })
                        continue

                    # Match votes
                    votes_match = votes_pattern.match(line)
                    if votes_match:
                        vote_type = votes_match.group(1)
                        votes = votes_match.group(2).replace(",", "")
                        percent = votes_match.group(3)
                        logging.info(f"Vote type matched: {vote_type}, Votes={votes}, Percent={percent}")
                        print(f"Vote type matched: {vote_type}")

                        if not current_office:
                            logging.warning(f"No office set for vote line: {line}")
                            print(f"Warning: No office set for vote line: {line}")
                            continue

                        if not current_party:
                            logging.warning(f"No party set for vote line: {line}")
                            print(f"Warning: No party set for vote line: {line}")
                            continue

                        meta_data[current_office] = meta_data.get(current_office, {})
                        meta_data[current_office][current_party] = meta_data[current_office].get(current_party, {})
                        meta_data[current_office][current_party][vote_type] = votes
                        meta_data[current_office][current_party][f"{vote_type} %"] = percent

                        if vote_type == "Under Votes" and candidate_array:
                            for candidate_row in candidate_array:
                                candidate_row["Cast Votes"] = meta_data[current_office][current_party].get("Cast Votes", "0")
                                candidate_row["Cast %"] = meta_data[current_office][current_party].get("Cast Votes %", "0.00%")
                                candidate_row["Over Votes"] = meta_data[current_office][current_party].get("Over Votes", "0")
                                candidate_row["Over %"] = meta_data[current_office][current_party].get("Over Votes %", "0.00%")
                                candidate_row["Under Votes"] = meta_data[current_office][current_party].get("Under Votes", "0")
                                candidate_row["Under %"] = meta_data[current_office][current_party].get("Under Votes %", "0.00%")
                                data.append(candidate_row)
                            candidate_array.clear()
                            logging.info(f"Added {len(data)} candidates to data for {current_office}")
                        continue

                    # Handle "No Candidate for Race"
                    if "No Candidate for Race" in line:
                        logging.info(f"No Candidate for Race detected")
                        print(f"No Candidate for Race detected")
                        candidate_array.append({
                            "Election": current_election or "Primary Election 2013",
                            "Date": current_date or "June 4, 2013",
                            "County": current_county or "Gloucester County",
                            "District": current_district or "",
                            "Precinct": extract_precinct(current_district),
                            "Office": current_office or "Unknown",
                            "Party": current_party,
                            "Candidate": "No Candidate",
                            "Election Day Votes": "0",
                            "Election Day %": "0.00%"
                        })
                        continue

                    # Log unmatched lines
                    logging.debug(f"Unmatched line on page {page_num}: {line}")
                    print(f"Unmatched line: {line}")

                # Save any remaining candidates at the end of the page
                if candidate_array:
                    for candidate_row in candidate_array:
                        candidate_row["Cast Votes"] = meta_data.get(current_office, {}).get(current_party, {}).get("Cast Votes", "0")
                        candidate_row["Cast %"] = meta_data.get(current_office, {}).get(current_party, {}).get("Cast Votes %", "0.00%")
                        candidate_row["Over Votes"] = meta_data.get(current_office, {}).get(current_party, {}).get("Over Votes", "0")
                        candidate_row["Over %"] = meta_data.get(current_office, {}).get(current_party, {}).get("Over Votes %", "0.00%")
                        candidate_row["Under Votes"] = meta_data.get(current_office, {}).get(current_party, {}).get("Under Votes", "0")
                        candidate_row["Under %"] = meta_data.get(current_office, {}).get(current_party, {}).get("Under Votes %", "0.00%")
                        data.append(candidate_row)
                    candidate_array.clear()
                    logging.info(f"Added {len(data)} candidates to data at end of page {page_num}")

    except FileNotFoundError:
        logging.error(f"PDF file not found: {pdf_path}")
        print(f"Error: PDF file not found at {pdf_path}")
        exit(1)


# Save data to CSV
if data:
    df = pd.DataFrame(data)
    df.to_csv(output_csv, index=False)
    logging.info(f"CSV file '{output_csv}' created with {len(df)} rows")
    print(f"CSV file '{output_csv}' created successfully with {len(df)} rows!")
    print(df.groupby("District").size())  # shows number of rows per district
    print(seen_districts)  # shows number of rows per district

else:
    logging.warning("No data extracted from the PDF")
    print("No data extracted from the PDF. Check 'pdf_extraction_single_column_v4_fixed.log' for details.")