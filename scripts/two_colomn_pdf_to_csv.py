# Unfinnished script desinged to split a pdf in text form.
# The PDF this scrip was desinged for had two columns that needed to be seperated and then flattend


#  pdf_path = "Woolwich Precinct Report.pdf"  

import pdfplumber
import pandas as pd
import re
import logging

# Set up logging
logging.basicConfig(filename='../logs/pdf_extraction_debug_v5.log', level=logging.DEBUG, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Paths
pdf_path = "Woolwich Precinct Report.pdf"  
output_csv = "2013_Primary_Election.csv"  # Output CSV file name

# Initialize data structures
data = []
candidate_array = []
meta_data = {}

# Regular expressions
header_election_pattern = re.compile(r"^(.*?)\s+(\d{4})\s+Primary Election\s*$")
header_date_pattern = re.compile(r"^(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\s*$")
header_precinct_pattern = re.compile(r"^Precinct Report\s*$")
header_county_pattern = re.compile(r"^Gloucester County\s*$")
header_district_pattern = re.compile(r"^(Woolwich\s+(?:District\s+\d+|Mail-In Ballot|Provisional))(?:\s+\1)?$")
contest_pattern = re.compile(r"^(REPB|DEMB|LIB|ACP)\s*-\s*(.*?)(?:\s+\(Final\))?\s*$")
candidate_pattern = re.compile(r"^(.*?)\s+(\d+,?\d*)\s+(\d+\.\d{2}%)(?:\s+.*)?$")
votes_pattern = re.compile(r"^(Election Day Turnout|Mail-In Ballot Turnout|Provisional Turnout|Cast Votes|Over Votes|Under Votes|Total\.\.\.)\s+(\d+,?\d*)\s+(\d+\.\d{2}%)(?:\s+.*)?$")

# Open the PDF
try:
    with pdfplumber.open(pdf_path) as pdf:
        current_election = ""
        current_date = ""
        current_precinct = ""
        current_district = ""
        current_office = ""
        current_party = "N/A"
        header_lines = []

        for page_num, page in enumerate(pdf.pages, 1):
            logging.info(f"Processing page {page_num}")
            print(f"\nProcessing page {page_num}...")

            # Extract raw text
            text = page.extract_text()
            if not text:
                logging.warning(f"No text extracted from page {page_num}")
                print(f"No text extracted from page {page_num}")
                continue

            logging.debug(f"Raw text for page {page_num}:\n{text}")
            print(f"Page {page_num} raw text sample (first 200 chars):\n{text[:200]}")

            # Split text into lines
            lines = text.split("\n")
            processed_lines = []
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                # Handle two-column merged lines
                if current_district and current_district in line and line.count(current_district) > 1:
                    parts = line.split(current_district, 1)
                    processed_lines.append(parts[0].strip() + current_district)
                    if parts[1].strip():
                        processed_lines.append(parts[1].strip())
                elif "Registration & Turnout" in line:
                    # Split merged contest lines (e.g., "Registration & Turnout 1,038 REPB - Woolwich Township Committee")
                    parts = line.split(" ", 3)
                    if len(parts) > 3 and "-" in parts[3]:
                        processed_lines.append(" ".join(parts[:3]))
                        processed_lines.append(parts[3])
                    else:
                        processed_lines.append(line)
                else:
                    processed_lines.append(line)

            for line in processed_lines:
                # Handle multi-line header
                if not (current_election and current_date and current_precinct and current_district):
                    header_lines.append(line)

                    # Match election
                    election_match = header_election_pattern.match(line)
                    if election_match:
                        current_election = election_match.group(1) + " " + election_match.group(2)
                        logging.info(f"Election matched: {current_election}")
                        print(f"Election matched: {current_election}")
                        continue

                    # Match date
                    date_match = header_date_pattern.match(line)
                    if date_match:
                        current_date = date_match.group(0)
                        logging.info(f"Date matched: {current_date}")
                        print(f"Date matched: {current_date}")
                        continue

                    # Match precinct
                    precinct_match = header_precinct_pattern.match(line)
                    if precinct_match:
                        current_precinct = "Gloucester County"
                        logging.info(f"Precinct matched: {current_precinct}")
                        print(f"Precinct matched: {current_precinct}")
                        continue

                    # Match district
                    district_match = header_district_pattern.match(line)
                    if district_match:
                        current_district = district_match.group(1)
                        logging.info(f"District matched: {current_district}")
                        print(f"District matched: {current_district}")
                        continue

                # Debug contest matching
                contest_match = contest_pattern.match(line)
                if contest_match:
                    current_office = contest_match.group(2).strip()
                    current_party = contest_match.group(1) if contest_match.group(1) else "N/A"
                    meta_data[current_office] = meta_data.get(current_office, {})
                    candidate_array.clear()
                    logging.info(f"Contest matched: Office={current_office}, Party={current_party}")
                    print(f"Contest matched: {current_office}")
                    continue

                # Debug candidate matching
                candidate_match = candidate_pattern.match(line)
                if candidate_match:
                    candidate_name = candidate_match.group(1).strip()
                    votes = candidate_match.group(2).replace(",", "")
                    percent = candidate_match.group(3)
                    logging.info(f"Candidate matched: {candidate_name}, Votes={votes}, Percent={percent}")
                    print(f"Candidate matched: {candidate_name}")

                    if not current_office:
                        logging.warning(f"No office set for candidate: {line}")
                        print(f"Warning: No office set for candidate: {line}")
                        continue

                    if not current_party:
                        logging.warning(f"No party set for candidate: {line}")
                        print(f"Warning: No party set for candidate: {line}")
                        continue

                    if current_party not in meta_data[current_office]:
                        meta_data[current_office][current_party] = {}

                    candidate_array.append({
                        "Election": current_election,
                        "Date": current_date,
                        "Precinct": current_precinct,
                        "District": current_district,
                        "Office": current_office,
                        "Party": current_party,
                        "Candidate": candidate_name,
                        "Election Day Votes": votes,
                        "Election Day %": percent,
                        "Mail-In Votes": "0",
                        "Mail-In %": "0.00%",
                        "Provisional Votes": "0",
                        "Provisional %": "0.00%",
                        "Cast Votes": "",
                        "Cast %": "",
                        "Over Votes": "",
                        "Over %": "",
                        "Under Votes": "",
                        "Under %": ""
                    })

                # Debug votes matching
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

                # Handle "No Candidate for Race"
                if "No Candidate for Race" in line:
                    logging.info(f"No Candidate for Race detected")
                    print(f"No Candidate for Race detected")
                    if not current_office:
                        logging.warning(f"No office set for No Candidate line: {line}")
                        print(f"Warning: No office set for No Candidate line: {line}")
                        continue
                    if not current_party:
                        logging.warning(f"No party set for No Candidate line: {line}")
                        print(f"Warning: No party set for No Candidate line: {line}")
                        continue
                    candidate_array.append({
                        "Election": current_election,
                        "Date": current_date,
                        "Precinct": current_precinct,
                        "District": current_district,
                        "Office": current_office,
                        "Party": current_party,
                        "Candidate": "No Candidate",
                        "Election Day Votes": "0",
                        "Election Day %": "0.00%",
                        "Mail-In Votes": "0",
                        "Mail-In %": "0.00%",
                        "Provisional Votes": "0",
                        "Provisional %": "0.00%",
                        "Cast Votes": "",
                        "Cast %": "",
                        "Over Votes": "",
                        "Over %": "",
                        "Under Votes": "",
                        "Under %": ""
                    })

                # Log unmatched lines
                if not (election_match or date_match or precinct_match or district_match or contest_match or candidate_match or votes_match or "No Candidate for Race" in line):
                    logging.debug(f"Unmatched line on page {page_num}: {line}")
                    print(f"Unmatched line: {line}")

except FileNotFoundError:
    logging.error(f"PDF file not found: {pdf_path}")
    print(f"Error: PDF file not found at {pdf_path}")
    exit(1)

# Save data to CSV
if data:
    df = pd.DataFrame(data)
    df = df.drop_duplicates(subset=["Election", "Precinct", "District", "Office", "Party", "Candidate", "Election Day Votes", "Mail-In Votes", "Provisional Votes"], keep="first")
    df.to_csv(output_csv, index=False)
    logging.info(f"CSV file '{output_csv}' created with {len(df)} rows")
    print(f"CSV file '{output_csv}' created successfully with {len(df)} rows!")
else:
    logging.warning("No data extracted from the PDF")
    print("No data extracted from the PDF. Check 'pdf_extraction_debug_v5.log' for details.")