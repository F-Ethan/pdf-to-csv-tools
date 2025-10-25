import pdfplumber
import re
import csv
import sys
import os
import logging
from typing import List, Dict
from pathlib import Path
import PyPDF2


# settings
input_folder = '../input'
output_csv = "../output/extracted_data.csv"

# Create logs directory first
os.makedirs('../logs', exist_ok=True)

log_file = "../logs/pdf_extraction.log"

# Early cleanup: Use print() since logging isn't set up yet
if os.path.exists(log_file):
    os.remove(log_file)
    print(f"File '{log_file}' deleted successfully.")  # Temp: Use print for early messages
else:
    print(f"File '{log_file}' does not exist.")

# Set up logging (force it to override defaults)
logging.basicConfig(
    force=True,  # Key fix: Python 3.8+; removes existing handlers and applies config
    filename=log_file,
    filemode="a",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logging.getLogger("pdfplumber").setLevel(logging.WARNING)
logging.info("Script started - logging initialized.")

OUTPUT_HEADERS = [
    "Event Date",
    "Event Type",
    "Precinct Name",
    "Vote Channel",
    "Candidate",
    "Total Votes",
    "Total Votes Cast",
    "District Name",
    "District Type",
    "Office",
    "Office Modifier",
    "# of winners",
    "Total Ballots Cast",
    "Over Votes",
    "Undervotes",
    "Ballots Cast",
    "County",
    "Raw Title",
    "Candidate Party",
]

# Extracted and deduplicated list of office terms from the original regex
office_terms = [
    "City",
    "Proposition",
    "Town",
    "Village",
    "School",
    "Representative",
    "Governor",
    "General",
    "Public",
    "Municipal Utility",
    "Supreme",
    "Clerk",
    "Attorney",
    "Court",
    "Board",
    "Judge",
    "Commissioner",
    "Member",
    "Justice",
    "Lieutenant",
    "Comptroller",
    "Railroad",
    "Senator",
    "Criminal",
    "Family",
    "Probate",
    "Peace",
    "Library",
    "Council",
    "Independent",
    "Councilmember",
    "Trustee",
    "District",
    "Place",
    "Comptroller",
    "Commissioner",
    "Chair",
    "County Constable"
]

compiled_patterns = []
for term in office_terms:
    pattern_str = r'^(.*)\b(' + re.escape(term) + r')\b(.*)$'
    compiled_pattern = re.compile(pattern_str)
    compiled_patterns.append(compiled_pattern)


# Patterns 
cast_pattern = re.compile(r'(?i)Cast Votes:\s+.+?\s+(\d{1,3}(?:,\d{3})*)\s+\d+\.\d+%$', re.IGNORECASE)
over_pattern = re.compile(r'(?i)Over Votes:\s+.+?\s+(\d+)\s+\d+\.\d+%$', re.IGNORECASE)
# Replace the existing patterns
precinct_pattern = re.compile(r'Precinct\s+(\d+)\s+\(Ballots Cast:\s*(\d{1,3}(?:,\d{3})*)\)', re.IGNORECASE)
# office_pattern = re.compile(r'^(.*?)\s*-\s*(.*?),\s*Vote\s+For\s*(\d+)$', re.IGNORECASE)
office_pattern = re.compile(r'^(.+?)\s+(.+?),\s*Vote\s+For\s*(\d+)$', re.IGNORECASE)
office_pattern_with_district = re.compile(r'^(.+?),\s*(District\s*#?\s*\d+)\s*City\s+of\s+(.+?),\s*Vote\s+For\s*(\d+)$', re.IGNORECASE)
office_pattern_no_district = re.compile(r'^(.+?)\s*(City|Town)\s+of\s+(.+?),\s*Vote\s+For\s*(\d+)$', re.IGNORECASE)


num_winners_patter = re.compile(r'^.*vote\sfor\s([\d+])', re.IGNORECASE)
cand_pattern = re.compile(r'^([A-Za-z.\s()]+?)\s+(\d+)\s+\d+\.\d+%\s+(\d+)\s+\d+\.\d+%\s+(\d+)\s+\d+\.\d+%\s+(\d+)\s+\d+\.\d+%$', re.IGNORECASE)
under_pattern = re.compile(r'(?i)Under Votes:\s+.+?\s+(\d+)\s+\d+\.\d+%$', re.IGNORECASE)
pattern_may = re.compile(r'May(\d{1,2}),\s*(\d{4})', re.IGNORECASE)
pattern_date = re.compile(r"(?:Event|Election)\s*Date[:\s]*(\d{1,2}/\d{1,2}/\d{4})", re.IGNORECASE)
pattern_date_fallback = re.compile(r"(\d{1,2}/\d{1,2}/\d{4})")
pattern_event = re.compile(r"(?:Event|Election)\s*Type[:\s]*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", re.IGNORECASE)
pattern_event_fallback = re.compile(r'—\s*([A-Z][a-z](?:\s+[A-Z][a-z]+)*?)\s*(?:Live|—)', re.IGNORECASE)
pattern_event_orig = re.compile(r'\b(Joint|General|Special|Primary|Election)\b', re.IGNORECASE)
pattern_county = re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(County|—)\b', re.IGNORECASE)
pattern_county_fallback = re.compile(r"(.+?)\s+County$", re.IGNORECASE)
pattern_total_ballots = re.compile(r"(?:Total\s+(?:Number\s+of\s+Voters|Ballots)\s*[:\s]*(\d{1,3}(?:,\d{3})*))", re.IGNORECASE)
pattern_total_ballots_fallback = re.compile(r"^Total Number of Voters : (\d{1,3}(?:,\d{3})*)\s+of\s+(\d{1,3}(?:,\d{3})*)\s+=\s+(\d+\.\d{2})%$")
pattern_total_ballots_fallback_two = re.compile(r"Ballots Cast[:\s]*(\d{1,3}(?:,\d{3})*)", re.IGNORECASE)
precinct_ballots_pattern = re.compile(r'\(Ballots Cast:(\d{1,3}(?:,\d{3})*)', re.IGNORECASE)


def extract_office_groups(text):
    """
    Extract the prefix, matched office term, and suffix from the input text.
    Returns (prefix, term, suffix) for the first match, or None if no match.
    """
    logging.info(f"Checking line for Office Groups: {text}")
    for pattern in compiled_patterns:
        match = pattern.search(text)
        if match:
            logging.info(f"Found office: {text}")
            prefix = match.group(1)
            term_matched = match.group(2)
            suffix = match.group(3)
            return (prefix, term_matched, suffix)  # Remove vote_total/group(4)
    return None


# parse_contest_name (unchanged)
def parse_contest_name(contest_name):
    phrases_tuple = (
        "Three Year Term",
        "Incumbent",
        "Unexpired Term"
        # Add more as needed
    )
    logging.info(f"Parsing line: {contest_name}")
    # Extract parentheses modifiers...
    paren_modifiers = re.findall(r"(\((?![^)]*At large)[^)]*\))", contest_name)
    
    # Build dynamic pattern for phrases...
    escaped_phrases = [re.escape(phrase) for phrase in phrases_tuple]
    phrases_or = "|".join(escaped_phrases) if escaped_phrases else ""
    
    if phrases_or:
        hyphen_phrase_pattern = re.compile(r"\s*-\s*(" + phrases_or + r")(?:\s|$)", re.IGNORECASE)
        hyphen_modifiers = hyphen_phrase_pattern.findall(contest_name)
        
        comma_phrase_pattern = re.compile(r"\s*,\s*(" + phrases_or + r")(?:\s|$)", re.IGNORECASE)
        comma_modifiers = comma_phrase_pattern.findall(contest_name)
        logging.info(f"Office modifiers: {comma_modifiers}")
    else:
        hyphen_modifiers = []
        comma_modifiers = []
        logging.info(f"No office modifiers")

    all_modifiers = paren_modifiers + hyphen_modifiers + comma_modifiers
    office_modifier = " ".join(all_modifiers) if all_modifiers else ""

    winners_match = num_winners_patter.search(contest_name)  # Add .search()!
    if winners_match:
        num_winners = winners_match.group(1).strip()
        logging.info(f"Number of winners: {num_winners}")
    else:
        num_winners = "NA"
        logging.warning(f"Number of winners not found")

    # Clean the name...
    clean_name = re.sub(r"\s*\([^)]*\)\s*", " ", contest_name)
    if phrases_or:
        clean_name = re.sub(r"\s*-\s*(?:" + phrases_or + r")(?:\s|$)", "", clean_name, flags=re.IGNORECASE)
        clean_name = re.sub(r"\s*,\s*(?:" + phrases_or + r")(?:\s|$)", "", clean_name, flags=re.IGNORECASE)
    clean_name = re.sub(r"\s+", " ", clean_name).strip()
    
    district_name = clean_name
    district_type = clean_name
    office = clean_name
    current_raw_office = contest_name  # Use the param name consistently
    
    logging.info(f"office breakdown: {office}, {district_name}, {district_type}")
    
    return office, district_name, district_type, office_modifier, current_raw_office, num_winners

def extract_event_date(line: str) -> str:
    # Specific for May DD, YYYY
    match_may = pattern_may.search(line)
    if match_may:
        day = match_may.group(1).zfill(2)
        year = match_may.group(2)
        logging.info(f"Date May matched: 05/{day}/{year} on line: {line}")
        return f"05/{day}/{year}"
    # Updated pattern to match date within line, e.g., "Election Date: MM/DD/YYYY"
    match = pattern_date.search(line)
    if match:
        logging.info(f"Date matched: {match.group(1)} on line: {line}")
        return match.group(1).strip()
    # Fallback to standalone date pattern
    match_fallback = pattern_date_fallback.search(line)
    if match_fallback:
        logging.info(f"Date fallback matched: {match_fallback.group(1)} on line: {line}")
        return match_fallback.group(1).strip()
    return ''

def extract_event_type(line: str) -> str:
    # Updated to match more flexibly, e.g., "Election Type: General Election"
    match = pattern_event.search(line)
    if match:
        logging.info(f"Event type matched: {match.group(1)} on line: {line}")
        return match.group(1).strip()
    # Fallback to keywords in the description
    match_fallback = pattern_event_fallback.search(line)
    if match_fallback:
        logging.info(f"Event type fallback matched: {match_fallback.group(1)} on line: {line}")
        return match_fallback.group(1).strip()
    # Original fallback
    match_orig = pattern_event_orig.search(line)
    if match_orig:
        logging.info(f"Event type orig fallback matched: {match_orig.group(1)} on line: {line}")
        return match_orig.group(1).strip()
    return ''

def extract_county(line: str) -> str:
    # Updated to match "XYZ County" within line, handling em dash if present
    match = pattern_county.search(line)
    if match:
        county_name = match.group(1).strip()
        logging.info(f"County matched: {county_name} {match.group(2)} on line: {line}")
        return f"{county_name} County".strip()
    # Fallback to line ending with County
    match_fallback = pattern_county_fallback.search(line)
    if match_fallback:
        logging.info(f"County fallback matched: {match_fallback.group(1).strip()} County on line: {line}")
        return f"{match_fallback.group(1).strip()} County"
    return ''

def extract_total_ballots_cast(line: str) -> str:
    # Updated pattern to be more flexible for ballots/voters line
    match = pattern_total_ballots.search(line)
    if match:
        logging.info(f"Total ballots matched: {match.group(1)} on line: {line}")
        return match.group(1).strip()
    # Fallback to the original specific pattern
    match_fallback = pattern_total_ballots_fallback.search(line)
    if match_fallback:
        logging.info(f"Total ballots fallback matched: {match_fallback.group(1)} on line: {line}")
        return match_fallback.group(1).strip()
    # Another fallback for ballots cast
    match_ballots = pattern_total_ballots_fallback_two.search(line)
    if match_ballots:
        logging.info(f"Ballots cast matched: {match_ballots.group(1)} on line: {line}")
        return match_ballots.group(1).strip()
    return ''

def save_contest(
    rows: List[Dict[str, str]],
    candidates: List[Dict[str, str]],
    contest: Dict[str, str],
    precinct: str,
    event_date: str,
    event_type: str,
    county: str,
    precinct_ballots_cast: str
):
    for cand in candidates:
        row = {
            "Event Date": event_date,
            "Event Type": event_type,
            "Precinct Name": precinct,
            "Vote Channel": cand.get("channel", ""),
            "Candidate": cand.get("candidate", ""),
            "Total Votes": cand.get("votes", ""),
            "Total Votes Cast": contest.get("total_votes_cast", ""),
            "District Name": contest.get("district_name", ""),
            "District Type": contest.get("district_type", ""),
            "Office": contest.get("office", ""),
            "Office Modifier": contest.get("office_modifier", ""),
            "# of winners": contest.get("num_winners", ""),
            "Total Ballots Cast": precinct_ballots_cast,
            "Over Votes": contest.get("over_votes", ""),
            "Undervotes": contest.get("undervotes", ""),
            "Ballots Cast": contest.get("ballots_cast", ""),
            "County": county,
            "Raw Title": contest.get("raw_title", ""),
            "Candidate Party": cand.get("party", ""),
        }
        rows.append(row)

def parse_pdf(pdf_path: str) -> List[Dict[str, str]]:
    rows = []
    pdf_file = Path(pdf_path)
    if not pdf_file.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    try:
        with pdfplumber.open(pdf_path) as pdf:
            if len(pdf.pages) == 0:
                logging.warning("PDF has no pages.")
                return rows

            # Parse first page for global info
            first_page = pdf.pages[0]
            first_text = first_page.extract_text()
            if first_text is None:
                logging.error("Failed to extract text from first page.")
                return rows
            first_lines = [line.strip() for line in first_text.split('\n') if line.strip()]
            logging.info(f"starting to process the page with #{len(first_lines)} lines")

            # Debug: Print first 20 lines to console for inspection
            # logging.info("First page lines for debugging:")
            # for idx, line in enumerate(first_lines[:20]):
            #     logging.info(f"Line {idx + 1}: {line}")
            # logging.info("\n")

            # In parse_pdf(), replace the entire for loop for first_lines:
            event_type = ''
            event_date = ''
            county = ''
            total_ballots_cast = ''

            for line in first_lines:
                # logging.info(f"Processing line: {line}")  # Keep for debug if needed
                logging.info(f"Processing line: {line}")
                
                # Check each without skipping the line
                if not event_type:
                    temp_type = extract_event_type(line)
                    if temp_type:
                        event_type = temp_type
                        # print(f"Found event_type: {event_type}")
                        logging.info(f"Found event_type: {event_type}")
                
                if not event_date:
                    temp_date = extract_event_date(line)
                    if temp_date:
                        event_date = temp_date
                        # print(f"Found event_date: {event_date}")
                        logging.info(f"Found event_date: {event_date}")
                
                if not county:
                    temp_county = extract_county(line)
                    if temp_county:
                        county = temp_county
                        # print(f"Found county: {county}")
                        logging.info(f"Found county: {county}")
                
                if not total_ballots_cast:
                    temp_ballots = extract_total_ballots_cast(line)
                    if temp_ballots:
                        total_ballots_cast = temp_ballots
                        # print(f"Found total_ballots_cast: {total_ballots_cast}")
                        logging.info(f"Found total_ballots_cast: {total_ballots_cast}")
                
                # Break early only if all are found
                if all([event_type, event_date, county, total_ballots_cast]):
                    break

            logging.info(f"Extracted global info: Date={event_date}, Type={event_type}, County={county}, Total Ballots={total_ballots_cast}")
            # print("Finished extracting global info")

            logging.info(f"Extracted global info: Date={event_date}, Type={event_type}, County={county}, Total Ballots={total_ballots_cast}")
            # print("Finished extracting global info")
            # Initialize for contests
            current_precinct = ""
            precinct_ballots_cast = ""
            current_contest = {}
            current_candidates = []

            for page_num in range(len(pdf.pages)):
                try:
                    page = pdf.pages[page_num]
                    text = page.extract_text()
                    if text is None:
                        logging.warning(f"Failed to extract text from page {page_num + 1}.")
                        continue
                    lines = [line.strip() for line in text.split('\n') if line.strip()]

                    # Debug: Print first few lines of each page
                    logging.info(f"\nPage {page_num + 1} first lines:")
                    for idx, line in enumerate(lines[:10]):
                        logging.info(f"  Line {idx + 1}: {line}")

                    i = 0
                    while i < len(lines):
                        line = lines[i]

                        precinct_match = precinct_pattern.search(line)
                        if precinct_match:
                            logging.info(f'Precinct Matched: {precinct_match}')
                            # Save previous contest if exists
                            if current_candidates:
                                save_contest(
                                    rows, current_candidates, current_contest, current_precinct,
                                    event_date, event_type, county, precinct_ballots_cast
                                )
                                logging.info(f"Saved contest for precinct {current_precinct}")
                                current_candidates = []
                                current_contest = {}

                            current_precinct = precinct_match.group(1).strip()
                            precinct_ballots_cast = precinct_match.group(2).strip()  # Capture directly
                            current_contest["ballots_cast"] = precinct_ballots_cast
                            logging.info(f"Precinct ballots: {precinct_ballots_cast}")
                            logging.debug(f"New precinct: {current_precinct}")
                            # print(f"Found precinct: {current_precinct}")
                            i += 1
                            continue


                        # if not current_precinct:
                        #     logging.warning(f"current_precinct not set on line {line}")
                        #     continue

                        contest_match = extract_office_groups(line)
                        if contest_match is not None:
                            office, district_name, district_type, office_modifier, raw_title, num_winners = parse_contest_name(line)
                            current_contest["office"] = office
                            current_contest["district_name"] = district_name
                            current_contest["district_type"] = district_type
                            current_contest["office_modifier"] = office_modifier
                            current_contest["raw_title"] = raw_title
                            current_contest["num_winners"] = num_winners
                            # DO NOT overwrite current_contest = line here!
                            logging.info(
                                f"Matched contest: {line}, office: {current_contest['office']}, district: {current_contest['district_name']}, "
                                f"type: {current_contest['district_type']}, modifier: {current_contest['office_modifier']}, winners: {num_winners}"
                            )
                            i += 1  # Add this!
                            continue

                        # Candidate line
                        cand_match = cand_pattern.match(line)
                        if cand_match and current_contest.get("office"):
                            name = cand_match.group(1).strip()
                            absentee_votes = cand_match.group(2).strip()
                            early_votes = cand_match.group(3).strip()
                            election_votes = cand_match.group(4).strip()
                            total_votes = cand_match.group(5).strip()

                            # Parse party if present
                            party_match = re.search(r'\s*\(([A-Z]+)\)', name)
                            party = ""
                            if party_match:
                                party = party_match.group(1)
                                name = re.sub(r'\s*\([^)]+\)', '', name).strip()

                            # Append for each channel
                            current_candidates.append({
                                "candidate": name,
                                "party": party,
                                "votes": absentee_votes,
                                "channel": "Absentee"
                            })
                            current_candidates.append({
                                "candidate": name,
                                "party": party,
                                "votes": early_votes,
                                "channel": "Early"
                            })
                            current_candidates.append({
                                "candidate": name,
                                "party": party,
                                "votes": election_votes,
                                "channel": "Election Day"
                            })
                            current_candidates.append({
                                "candidate": name,
                                "party": party,
                                "votes": total_votes,
                                "channel": "Total"
                            })
                            logging.info(f"Found candidate: {name} ({party}) - Absentee: {absentee_votes}, Early: {early_votes}, Election: {election_votes}, Total: {total_votes}")
                            i += 1
                            continue
                        else:
                            if not current_precinct:  # Only warn if trying to parse candidates without precinct
                                logging.error(f"No precinct found on page: {page_num + 1}")
                                # print(f"error no precinct detected on page: {page_num + 1}")

                        # Cast Votes total (last number before %)
                        cast_match = cast_pattern.search(line)
                        if cast_match:
                            current_contest["total_votes_cast"] = cast_match.group(1).strip()
                            logging.info(f"Found cast votes total: {cast_match.group(1)}")
                            i += 1
                            continue

                        # Over Votes total (last number before %)
                        over_match = over_pattern.search(line)
                        if over_match:
                            current_contest["over_votes"] = over_match.group(1).strip()
                            logging.info(f"Found over votes total: {over_match.group(1)}")
                            i += 1
                            continue

                        # Undervotes - trigger save, total last number
                        under_match = under_pattern.search(line)
                        if under_match:
                            current_contest["undervotes"] = under_match.group(1).strip()
                            logging.info(f"Found undervotes total: {under_match.group(1)} - saving contest")
                            # Save the contest
                            save_contest(
                                rows, current_candidates, current_contest, current_precinct,
                                event_date, event_type, county, precinct_ballots_cast
                            )
                            current_candidates = []
                            current_contest = {}
                            i += 1
                            continue

                        if not current_precinct:
                            logging.error(f"No precinct found on page: {page_num + 1}")
                            print(f"error no precinct detectad on page: {page_num + 1}")
                            # break

                        i += 1


                except Exception as e:
                    logging.error(f"Error processing page {page_num + 1}: {e}")
                    continue

            # Save any remaining contest at the end
            if current_candidates:
                save_contest(
                    rows, current_candidates, current_contest, current_precinct,
                    event_date, event_type, county, precinct_ballots_cast
                )
                logging.info(f"Saved final contest for precinct {current_precinct}")

    except Exception as e:
        logging.error(f"Unexpected error during PDF parsing: {e}")
        raise

    return rows

def main():
    pdf_files = [
        os.path.join(input_folder, f)
        for f in os.listdir(input_folder)
        if f.lower().endswith(".pdf")
    ]

    if not pdf_files:
        logging.info(f"No PDF files found in '{input_folder}'.")
        sys.exit(1)

    # Clean up output files if exist (now logging works)
    if os.path.exists(output_csv):
        os.remove(output_csv)
        logging.info(f"File '{output_csv}' deleted successfully.")
    else:
        logging.info(f"File '{output_csv}' does not exist.")



    # Open CSV once and write header
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
   
    with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=OUTPUT_HEADERS)
        writer.writeheader()

        accumulated_rows = []
        batch_pages = 0
        total_rows = 0  # Retained for potential logging use

        for pdf_path in pdf_files:
            logging.info(f"\nProcessing {pdf_path}...")
            try:
                extracted_rows = parse_pdf(pdf_path)
                
                # Get the number of pages in the PDF
                with open(pdf_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    num_pages = len(reader.pages)
                
                accumulated_rows.extend(extracted_rows)
                batch_pages += num_pages
                total_rows += len(extracted_rows)
                
                logging.info(f"Processed {pdf_path}: {len(extracted_rows)} rows, {num_pages} pages.")
                print(f"Extracted {len(extracted_rows)} rows from {pdf_path} ({num_pages} pages).")
                
                # Save (flush) once every 25 pages
                if batch_pages >= 25:
                    writer.writerows(accumulated_rows)
                    logging.info(f"Saved batch of {len(accumulated_rows)} rows after {batch_pages} pages.")
                    print(f"Saved batch after reaching {batch_pages} pages.")
                    accumulated_rows = []
                    batch_pages = 0
                    
            except FileNotFoundError as e:
                logging.error(str(e))
                print(f"Error: {e}")
                continue
            except Exception as e:
                logging.error(f"Failed to process {pdf_path}: {e}")
                print(f"Error processing {pdf_path}: {e}")
                continue
        
        # Save any remaining rows after processing all PDFs
        if accumulated_rows:
            writer.writerows(accumulated_rows)
            logging.info(f"Saved final batch of {len(accumulated_rows)} rows after {batch_pages} pages.")
            print(f"Saved final batch after {batch_pages} remaining pages.")

        logging.info(f"Total extraction complete. {total_rows} rows written to {output_csv}.")
        print(f"\nExtraction complete. Total {total_rows} rows saved to {output_csv}.")


if __name__ == "__main__":
    main()