import pdfplumber
import pandas as pd
import re
import logging
import os
import psutil
import gc
import time
from collections import defaultdict
from multiprocessing import Pool, cpu_count
from functools import partial

"""
    This script is desinged to pull out and flatten all the data from a folder of
    precinct level PDF's and output all the information in a single CSV. 
    Set muti thread to ture for faster processing
    set in_development to true to only process the frist 10 pages
    batch_size, memory_limit_mb, system_memory_limit_mb are all there to keep the memory load down
    however currently the latter two are not being checked as they didn't ever work properly

    Make sure to check the contest_pattern regex it may need changed before it will match with the offices in a new events. 

"""

# Configuration
in_development = False  # Set to True to process only the first 10 pages per PDF
multi_thread = True
input_folder = "../input"  # Update to your folder path
output_csv = "../output/Election_Results.csv"
debug_page_range = None  # Set to (start, end) for debugging, e.g., (600, 640)
batch_size = 300  # Write to CSV every X pages (now per-file, not per-process)
memory_limit_mb = 500  # Per-process memory limit in MB
system_memory_limit_mb = (
    8000  # System-wide used memory limit in MB (adjust based on your RAM)
)
party_by_file = False #[
    # "",
    # "Dem",
    # "Rep",
#]  # Set this to true it the Parties are sepperated by file
current_file_count = None

# Set up logging
logging.basicConfig(
    filename="logs/pdf_extraction.log",
    filemode="a",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logging.getLogger("pdfplumber").setLevel(logging.WARNING)
logging.info("We are all set!")

# Output headers
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

# Regular expressions (unchanged except for candidate party)
# (\d{1,3}(?:,\d{3})*)  -- this should match any number 1-999 and 1,000 + including the coma
# (\d{1,3}(?:,\d{3})*|\d+) -- this will match with coma and without

date_pattern = re.compile(
    r"^(0[1-9]|1[0-2]|[1-9])\/([1-9]|0[1-9]|[12][0-9]|3[01])\/(19|20)\d{2}$"
)
ballots_cast_pattern = re.compile(r"^(\d+)\s+of\s+(\d+)\s+=\s+\d+\.\d{2}%$")
county_pattern = re.compile(r"^(.*?\s*County)$", re.IGNORECASE)
# contest_pattern = re.compile(
#     r"^(.*\b(City|Proposition|Town|Village|School|Representative|Governor|General|Public|Municipal Utility|Supreme|Clerk|Attorney|Court|Board|Judge|Commissioner|Member|Justice|Lieutenant|Comptroller|Railroad|Senator|Criminal|Family|Probate|Peace|Library|Council|Independent|Councilmember|Trustee|District|Place)\b.*|Comptroller of Public Accounts|Commissioner of the General Land Office|Commissioner of Agriculture|Councilmember|Precinct Chair,.*|County Constable,.*)$"
#     )

# Match lines like: "123 456 ballots cast"
precinct_pattern = re.compile(
    r"^(\d{1,3}(?:,\d{3})*|\d+\s+-\s+\d{1,3}(?:,\d{3})*|\d+)\s+(\d{1,3}(?:,\d{3})*|\d+)\s+ballots cast"
)
precinct_pattern_numeric = re.compile(
    r"^(\d+)\s+(\d{1,3}(?:,\d{3})*)\s+of\s+(\d{1,3}(?:,\d{3})*)\s+registered voters\s+=\s+(\d+\.\d{2})%$"
)
# Match lines like: "123 456 of 1,234 registered voters = 98.76%"
precinct_pattern_general = re.compile(
    r"^(\d+\s*-\s*[A-Za-z0-9]+)\s+(\d{1,3}(?:,\d{3})*)\s+of\s+(\d{1,3}(?:,\d{3})*)\s+registered voters\s+=\s+(\d+\.\d{2})%$"
)
# Match lines like: "Cast Votes ... 12,345 67.89%"
total_votes_pattern = re.compile(r"Cast Votes.*\s+(\d{1,3}(?:,\d{3})*)\s+\d+\.\d{2}%$")
# Match lines like: "Overvotes: 0 0 0 123"
over_votes_pattern = re.compile(
    r"Overvotes:\s+(?:\d{1,3}(?:,\d{3})*\s+)*(\d{1,3}(?:,\d{3})*)$"
)
undervotes_pattern = re.compile(
    r"Undervotes:\s+(?:\d{1,3}(?:,\d{3})*\s+)*(\d{1,3}(?:,\d{3})*)$"
)
# Pattern to extract vote and percent pairs
vote_percent_pattern = re.compile(r"(\d{1,3}(?:,\d{3})*)\s+(\d+\.\d{2})%")

def extract_office_groups(text):
    """
    Extract the prefix, matched office term, and suffix from the input text.
    Returns (prefix, term, suffix) for the first match, or None if no match.
    """
    logging.info(f"Checking line for Office Groups: {text}")
    for pattern in compiled_patterns:
        match = pattern.search(text)
        if match:
            prefix = match.group(1)
            term_matched = match.group(2)
            suffix = match.group(3)
            return (prefix, term_matched, suffix)
    return None


# Function to parse candidate party (added 'W' for write-ins)
def parse_candidate_line(line, current_file_count=None):
    """
    Parses a candidate line like:
    'Eric Starnes REP 26 46.43% 749 58.88% 406 59.97% 1,181 58.90%'

    Returns:
        candidate_name (str), candidate_party (str), results (List[Tuple[int, float]])
    """
    # Extract everything before the first vote number
    # This assumes candidate name + party come before vote/percent pairs
    candidate_info_match = re.match(
        r"^(?!.*Cast Votes:)(.+?)\s+(?=\d{1,3}(?:,\d{3})*\s+\d+\.\d{2}%)", line
    )
    if not candidate_info_match:
        return None

    candidate_info = candidate_info_match.group(1).strip()

    # Extract party from candidate_info using your original function's logic
    candidate_groups_pattern = re.compile(r"^(.*)\s+(REP|DEM|LIB|GRE|IND|W)$")
    candidate_groups = candidate_groups_pattern.match(candidate_info)
    if candidate_groups:
        candidate_name = candidate_groups.group(1).strip()
        candidate_party = candidate_groups.group(2)
    else:
        candidate_name = candidate_info
        # if the candidates are seperated by file this will set the candidate party by the file count.
        if party_by_file:
            candidate_party = party_by_file[current_file_count]
        else:
            candidate_party = ""
            logging.warning(f"No party found for candidate: {candidate_info}")

    # Parse all vote/percent pairs from the remainder of the line
    rest = line[candidate_info_match.end() :]
    results = []
    for vote_str, percent_str in vote_percent_pattern.findall(rest):
        try:
            vote_count = int(vote_str.replace(",", ""))
            percent = float(percent_str)
            results.append((vote_count, percent))
        except ValueError:
            logging.warning(
                f"Invalid vote or percent format: {vote_str}, {percent_str}"
            )

    return candidate_name, candidate_party, results


# parse_contest_name (unchanged)
def parse_contest_name(contest_name):
    phrases_tuple = (
        "Three Year Term",
        "Incumbent",
        # Add more, e.g., "Proposition A", "Place 1"
    )

    # Extract parentheses modifiers with negative lookahead to exclude those containing "At large"
    paren_modifiers = re.findall(r"(\((?![^)]*At large)[^)]*\))", contest_name)
    
    # Build dynamic pattern for phrases (optionally after hyphen or comma)
    if phrases_tuple:
        escaped_phrases = [re.escape(phrase) for phrase in phrases_tuple]
        phrases_or = "|".join(escaped_phrases)
        # Pattern for hyphen: optional hyphen + space + phrase (non-greedy, at end or isolated)
        hyphen_phrase_pattern = re.compile(r"\s*-\s*(" + phrases_or + r")(?:\s|$)", re.IGNORECASE)
        hyphen_modifiers = hyphen_phrase_pattern.findall(contest_name)
        
        # Pattern for comma: optional comma + space + phrase (non-greedy, at end or isolated)
        comma_phrase_pattern = re.compile(r"\s*,\s*(" + phrases_or + r")(?:\s|$)", re.IGNORECASE)
        comma_modifiers = comma_phrase_pattern.findall(contest_name)
    else:
        hyphen_modifiers = []
        comma_modifiers = []
    
    # Combine all modifiers (as list, then join for string)
    all_modifiers = paren_modifiers + hyphen_modifiers + comma_modifiers
    office_modifier = " ".join(all_modifiers) if all_modifiers else ""
    
    # Clean the name: remove parens, hyphen-phrases, and comma-phrases
    # Note: We still remove all parens during cleaning, even excluded ones, to avoid them in clean_name
    clean_name = re.sub(r"\s*\([^)]*\)\s*", " ", contest_name)  # Remove all parens
    clean_name = re.sub(r"\s*-\s*(?:" + phrases_or + r")(?:\s|$)", "", clean_name, flags=re.IGNORECASE)  # Remove hyphen-phrases
    clean_name = re.sub(r"\s*,\s*(?:" + phrases_or + r")(?:\s|$)", "", clean_name, flags=re.IGNORECASE)  # Remove comma-phrases
    clean_name = re.sub(r"\s+", " ", clean_name).strip()
    
    # clean_name = re.sub(r",\s*Place\s+[1-9][0-9]?\s*", " ", clean_name)
    district_name = clean_name
    district_type = clean_name
    office = clean_name
    current_raw_office = contest_name
    
    return office, district_name, district_type, office_modifier, current_raw_office
    # if "City of" in clean_name:
    #     district_type = "City"
    #     parts = clean_name.split("City of", 1)
    #     if len(parts) > 1:
    #         district_name = (
    #             parts[1].split("Proposition")[0].strip()
    #             if "Proposition" in parts[1]
    #             else parts[1].strip()
    #         )
    #         office = (
    #             "Proposition " + parts[1].split("Proposition")[1].strip()
    #             if "Proposition" in parts[1]
    #             else clean_name
    #         )
    # elif "Town of" in clean_name:
    #     district_type = "Town"
    #     parts = clean_name.split("Town of", 1)
    #     if len(parts) > 1:
    #         district_name = (
    #             parts[1].split("Proposition")[0].strip()
    #             if "Proposition" in parts[1]
    #             else parts[1].strip()
    #         )
    #         office = (
    #             "Proposition " + parts[1].split("Proposition")[1].strip()
    #             if "Proposition" in parts[1]
    #             else clean_name
    #         )
    # elif "State of Texas" in clean_name:
    #     district_type = "State"
    #     district_name = "Texas"
    #     office = clean_name.replace("State of Texas", "").strip()
    # elif "Tarrant County" in clean_name:
    #     district_type = "County"
    #     district_name = "Tarrant"
    #     office = clean_name.replace("Tarrant County", "").strip()
    # elif "Proposition" in clean_name:
    #     district_type = "County"
    #     district_name = "Tarrant"
    #     office = clean_name
    # elif "School" in clean_name:
    #     district_type = "School"
    #     district_name = (
    #         clean_name.split("School")[0].strip() if "School" in clean_name else ""
    #     )
    #     office = clean_name
    # else:
    #     district_type = clean_name
    #     district_name = clean_name
    #     office = clean_name
    # return office, district_name, district_type, office_modifier, current_raw_office


# group_words_into_lines
def group_words_into_lines(words):
    lines = defaultdict(list)
    for word in words:
        y = round(word["top"], 1)
        lines[y].append(word)
    sorted_lines = []
    for y in sorted(lines.keys()):
        sorted_words = sorted(lines[y], key=lambda w: w["x0"])
        line_text = " ".join(word["text"] for word in sorted_words if word["text"])
        sorted_lines.append(line_text.strip())
    return sorted_lines


# save_data_to_csv (removed lock; now called only from main)
def save_data_to_csv(data, output_csv, append=True):
    logging.info(f"Attempting to save {len(data)} rows to {output_csv}")
    start_time = time.time()
    if data:
        logging.info(
            f"Sample row for debug: {data[0]}"
        )  # Log first row for verification
        print(f"Saving Data: {data[0]['Precinct Name']}")
        df = pd.DataFrame(data, columns=OUTPUT_HEADERS)
        mode = "a" if append and os.path.exists(output_csv) else "w"
        df.to_csv(
            output_csv,
            index=False,
            mode=mode,
            header=not append or not os.path.exists(output_csv),
        )
        logging.info(
            f"Saved {len(data)} rows to {output_csv} in {time.time() - start_time:.2f} seconds"
        )
        del df
    else:
        logging.warning("No data to save to CSV")
    gc.collect()
    return []


def process_page_range(pdf_path, page_range, header_data=None, current_file_count=None):
    data = []
    pages_processed = 0
    try:
        with pdfplumber.open(pdf_path) as pdf:
            current_event_date = (
                header_data.get("event_date", "") if header_data else ""
            )
            current_event_type = (
                header_data.get("event_type", "") if header_data else ""
            )
            current_county = header_data.get("county", "") if header_data else ""
            current_total_ballots_cast = (
                header_data.get("total_ballots_cast", "") if header_data else ""
            )
            current_precinct = None
            current_precinct_ballots = "0"
            current_office = ""
            current_district_name = ""
            current_district_type = ""
            current_office_modifier = ""
            current_raw_office = ""
            current_contest = None

            for page_num in page_range:
                start_time = time.time()  # start_time inside loop for per-page timing
                try:
                    if page_num % 100 == 0 or page_num == 1:
                        print(f"Starting to process page: {page_num}")

                    logging.info(f"Processing page {page_num} of {pdf_path}")
                    page = pdf.pages[page_num - 2]

                    # Extract header info
                    if page_num == 1 and not header_data:
                        extract_start = time.time()
                        text = page.extract_text()
                        lines = text.split("\n") if text else []
                        for line in lines[:10]:
                            line = line.strip()
                            if date_pattern.match(line):
                                current_event_date = line
                            if county_pattern.match(line):
                                current_county = line
                            if line == "Ballots Cast" and lines.index(line) + 1 < len(
                                lines
                            ):
                                next_line = lines[lines.index(line) + 1].strip()
                                if next_line.isdigit():
                                    current_total_ballots_cast = next_line
                            if "Registered Voters" in line and lines.index(
                                line
                            ) + 1 < len(lines):
                                next_line = lines[lines.index(line) + 1].strip()
                                match = ballots_cast_pattern.match(next_line)
                                if match:
                                    current_total_ballots_cast = match.group(1)
                            if "Election" in line and "Precincts Reporting" not in line:
                                current_event_type = line
                        logging.info(
                            f"Page {page_num} text extraction took {time.time() - extract_start:.2f} seconds"
                        )

                    # Extract lines
                    extract_start = time.time()
                    lines = []
                    text = page.extract_text()
                    if text:
                        lines = [
                            line.strip() for line in text.split("\n") if line.strip()
                        ]
                    if not lines:
                        try:
                            words = page.extract_words()
                            lines = group_words_into_lines(words) if words else []
                        except Exception as e:
                            logging.error(
                                f"Failed to extract words on page {page_num}: {str(e)}"
                            )
                            continue
                    logging.info(
                        f"Page {page_num} extraction took {time.time() - extract_start:.2f} seconds"
                    )
                    if not lines:
                        logging.warning(f"No text extracted on page {page_num}")
                        continue
                    if in_development or page_num % 1000 == 0:
                        logging.info(f"Extracted lines on page {page_num}: {lines}")

                    # First pass: Collect summary data (unchanged)
                    regex_start = time.time()
                    contest_summaries = {}
                    for line in lines:
                        if not line:
                            continue
                        contest_match = extract_office_groups(line)
                        if contest_match is not None:
                            current_contest = line
                            contest_summaries[current_contest] = {
                                "total_votes_cast": "N/A",
                                "over_votes": "N/A",
                                "undervotes": "N/A",
                            }
                            logging.info(f"Set current_contest: {current_contest}")
                            continue
                        total_match = total_votes_pattern.search(line)
                        if total_match and current_contest:
                            contest_summaries[current_contest]["total_votes_cast"] = (
                                total_match.group(1)
                            )
                            logging.info(
                                f"Total votes cast for {current_contest}: {total_match.group(1)}"
                            )
                            continue
                        over_match = over_votes_pattern.search(line)
                        if over_match and current_contest:
                            contest_summaries[current_contest]["over_votes"] = (
                                over_match.group(1)
                            )
                            logging.info(
                                f"Over votes for {current_contest}: {over_match.group(1)}"
                            )
                            continue
                        under_match = undervotes_pattern.search(line)
                        if under_match and current_contest:
                            contest_summaries[current_contest]["undervotes"] = (
                                under_match.group(1)
                            )
                            logging.info(
                                f"Under votes for {current_contest}: {under_match.group(1)}"
                            )
                            continue
                        precinct_match = precinct_pattern.match(line)
                        if precinct_match:
                            current_precinct = precinct_match.group(1)
                            current_precinct_ballots = precinct_match.group(2)
                            logging.info(
                                f"Found precinct (alt: 1): {current_precinct}, ballots: {current_precinct_ballots}"
                            )
                            continue
                        precinct_match_numeric = precinct_pattern_numeric.match(line)
                        if precinct_match_numeric:
                            current_precinct = precinct_match_numeric.group(1)
                            current_precinct_ballots = precinct_match_numeric.group(2)
                            logging.info(
                                f"Found precinct (numeric): {current_precinct}, ballots: {current_precinct_ballots}"
                            )
                            continue
                        precinct_match_two = precinct_pattern_general.match(line)
                        if precinct_match_two:
                            current_precinct = precinct_match_two.group(1)
                            current_precinct_ballots = precinct_match_two.group(2)
                            logging.info(
                                f"Found precinct (alt: 2): {current_precinct}, ballots: {current_precinct_ballots}"
                            )
                            continue
                    logging.info(
                        f"Page {page_num} regex processing took {time.time() - regex_start:.2f} seconds"
                    )

                    # Second pass: Process candidates
                    for line in lines:
                        if not line:
                            continue

                        logging.info(f"Testing line: {line}")
                        contest_match = extract_office_groups(line)
                        if contest_match is not None:
                            (
                                current_office,
                                current_district_name,
                                current_district_type,
                                current_office_modifier,
                                current_raw_office,
                            ) = parse_contest_name(line)
                            current_contest = line
                            logging.info(
                                f"Matched contest: {line}, office: {current_office}, district: {current_district_name}, type: {current_district_type}, modifier: {current_office_modifier}"
                            )
                            continue

                        if not current_precinct:
                            logging.warning(
                                f"Candidate line without precinct set: {line}"
                            )
                        parsed = parse_candidate_line(
                            line, current_file_count=current_file_count
                        )
                        if parsed:
                            candidate, current_candidate_party, results = parsed
                            absentee_votes = results[0][0] if len(results) > 0 else 0
                            early_votes = results[1][0] if len(results) > 1 else 0
                            election_day_votes = (
                                results[2][0] if len(results) > 2 else 0
                            )
                            total_votes = results[3][0] if len(results) > 3 else 0
                            try:
                                absentee_votes_int = int(absentee_votes)
                                early_votes_int = int(early_votes)
                                election_day_votes_int = int(election_day_votes)
                                total_votes_int = int(total_votes)
                                totals_check = total_votes_int == (
                                    absentee_votes_int
                                    + early_votes_int
                                    + election_day_votes_int
                                )
                                if not totals_check:
                                    logging.warning(
                                        f"Vote totals mismatch for {candidate} in {current_contest}: {total_votes_int} != {absentee_votes_int} + {early_votes_int} + {election_day_votes_int}"
                                    )
                            except ValueError:
                                logging.error(
                                    f"Invalid vote counts for {candidate} in {current_contest}: {line}"
                                )
                                continue
                            vote_channels = {
                                "Absentee": absentee_votes,
                                "Early": early_votes,
                                "Election Day": election_day_votes,
                                "Total": total_votes,
                            }
                            total_votes_cast = contest_summaries.get(
                                current_contest, {}
                            ).get("total_votes_cast", "N/A")
                            over_votes = contest_summaries.get(current_contest, {}).get(
                                "over_votes", "N/A"
                            )
                            undervotes = contest_summaries.get(current_contest, {}).get(
                                "undervotes", "N/A"
                            )
                            if current_contest is None:
                                logging.warning(
                                    f"No contest set for candidate {candidate} on page {page_num}: {line}"
                                )
                                continue
                            for channel, votes in vote_channels.items():
                                row = {
                                    "Event Date": current_event_date or "N/A",
                                    "Event Type": current_event_type or "N/A",
                                    "Precinct Name": current_precinct or "N/A",
                                    "Vote Channel": channel,
                                    "Candidate": candidate,
                                    "Total Votes": votes,
                                    "Total Votes Cast": total_votes_cast,
                                    "District Name": current_district_name,
                                    "District Type": current_district_type,
                                    "Office": current_office,
                                    "Office Modifier": current_office_modifier,
                                    "# of winners": "1",
                                    "Total Ballots Cast": current_total_ballots_cast
                                    or "N/A",
                                    "Over Votes": over_votes,
                                    "Undervotes": undervotes,
                                    "Ballots Cast": current_precinct_ballots,
                                    "County": current_county or '',
                                    "Raw Title": current_raw_office,
                                    "Candidate Party": current_candidate_party,
                                }
                                data.append(row)
                                logging.info(
                                    f"Appended row: {candidate}, {channel}, {votes}, total_votes_cast: {total_votes_cast}, Precinct: {current_precinct}"
                                )
                        else:
                            logging.debug(f"Candidate pattern did not match: {line}")
                    contest_summaries.clear()
                    page.close()
                    gc.collect()
                    pages_processed += 1  # Fix: Increment after processing

                    # Refresh memory info here, after appending data (no batch save)
                    process = psutil.Process()
                    mem_info = process.memory_info()
                    logging.info(
                        f"Page {page_num} memory usage: {mem_info.rss / 1024 / 1024:.2f} MB"
                    )
                    system_mem_used = psutil.virtual_memory().used / 1024 / 1024
                    logging.info(f"System memory used: {system_mem_used:.2f} MB")

                    logging.info(
                        f"Page {page_num} total processing time: {time.time() - start_time:.2f} seconds"
                    )

                except Exception as e:
                    logging.error(
                        f"Error processing page {page_num} in {pdf_path}: {str(e)}"
                    )
                    continue
            logging.info(f"Data list size before return: {len(data)}")
            return data, {
                "event_date": current_event_date,
                "event_type": current_event_type,
                "county": current_county,
                "total_ballots_cast": current_total_ballots_cast,
            }
    except Exception as e:
        logging.error(
            f"Error processing {pdf_path} pages {page_range[0]}-{page_range[-1]}: {str(e)}"
        )
        return [], {}


# Main processing function
def main():
    pdf_files = [
        os.path.join(input_folder, f)
        for f in os.listdir(input_folder)
        if f.lower().endswith(".pdf")
    ]
    if os.path.exists(output_csv):
        os.remove(output_csv)
        print(f"File '{output_csv}' deleted successfully.")
    else:
        print(f"File '{output_csv}' does not exist.")
    if os.path.exists("logs/pdf_extraction.log"):
        os.remove("logs/pdf_extraction.log")
        print(f"File 'pdf_extraction.log' deleted successfully.")
    else:
        print(f"File 'pdf_extraction.log' does not exist.")

    print(
        "Good morning! If you are seeing this, we are opening the file and it is taking a few minutes. Please just be patient."
    )
    file_index = 0
    append_to_csv = False  # Start with False to write headers
    for pdf_path in pdf_files:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                max_pages = 10 if in_development else len(pdf.pages)
                print("start of it all")
                if debug_page_range:
                    start, end = debug_page_range
                    page_range_sum = end - start
                    processes = cpu_count() if multi_thread else 1
                    chunk_size = (
                        max_pages
                        if not multi_thread
                        else page_range_sum // processes + 1
                    )
                    # page_ranges = [
                    #     range(max(1, start), min(end + 1, len(pdf.pages) + 1))
                    # ]
                    page_ranges = [
                        range(i, min(i + chunk_size, end + 1))
                        for i in range(start, end + 1, chunk_size)
                    ]
                    print("debug_page_range active")
                else:
                    # processes = cpu_count() if multi_thread else 1
                    # chunk_size = max_pages if not multi_thread else max_pages // processes + 1
                    # page_ranges = [range(i + 1, min(i + chunk_size + 1, max_pages + 1)) for i in range(0, max_pages, chunk_size)]
                    # print("getting groups ready")

                    group_count = 8
                    processes = cpu_count() if multi_thread else 1
                    precinct_starts = (
                        [p for p in range(1, max_pages + 1) if p % processes == 1]
                        if multi_thread
                        else [1]
                    )

                    # Divide precinct_starts into 8 roughly even groups
                    # Ensure we have at least 8 starts, or reduce the group count accordingly
                    available_groups = min(group_count, len(precinct_starts))
                    step = len(precinct_starts) // available_groups

                    # Select 8 evenly spaced precinct starts
                    selected_starts = [
                        precinct_starts[i * step] for i in range(available_groups)
                    ]

                    # Create page ranges from selected starts
                    page_ranges = []
                    for i in range(len(selected_starts)):
                        start = selected_starts[i]
                        if i + 1 < len(selected_starts):
                            end = (
                                selected_starts[i + 1] - 1
                            )  # end before the next start
                        else:
                            end = (
                                max_pages  # last chunk goes to the end of the document
                            )
                        page_ranges.append(range(start, end + 1))
                # print(f"Logging page ranges here {[list(r) for r in page_ranges]}")

                logging.info(f"Selected page ranges: {[list(r) for r in page_ranges]}")

                header_data = {}
                logging.info(f"First page: {page_ranges[0][0]} ")

                if page_ranges and page_ranges[0][0] == 1:
                    first_page = pdf.pages[0]
                    text = first_page.extract_text()
                    lines = text.split("\n") if text else []
                    for line in lines[:10]:
                        line = line.strip()
                        if date_pattern.match(line):
                            header_data["event_date"] = line
                        if county_pattern.match(line):
                            header_data["county"] = line
                        if line == "Ballots Cast" and lines.index(line) + 1 < len(
                            lines
                        ):
                            next_line = lines[lines.index(line) + 1].strip()
                            if next_line.isdigit():
                                header_data["total_ballots_cast"] = next_line
                        if "Registered Voters" in line and lines.index(line) + 1 < len(
                            lines
                        ):
                            next_line = lines[lines.index(line) + 1].strip()
                            match = ballots_cast_pattern.match(next_line)
                            if match:
                                header_data["total_ballots_cast"] = match.group(1)
                        if "Election" in line and "Precincts Reporting" not in line:
                            header_data["event_type"] = line
                    first_page.close()

                logging.info(f"First paage processed: {header_data} ")

                pool = Pool(processes=processes)
                try:
                    results = pool.starmap(
                        partial(
                            process_page_range,
                            pdf_path,
                            header_data=header_data,
                            current_file_count=file_index,
                        ),
                        [(pr,) for pr in page_ranges],
                    )

                    all_data = []
                    for data_chunk, _ in results:
                        all_data.extend(data_chunk)
                    logging.info(f"Collected {len(all_data)} rows from all page ranges")
                    if all_data:
                        # Optional: Save in batches if very large
                        for i in range(0, len(all_data), batch_size):
                            batch = all_data[i:i + batch_size]
                            save_data_to_csv(batch, output_csv, append=append_to_csv)
                            append_to_csv = True  # After first batch, append
                        print(
                            f"CSV file '{output_csv}' updated with {len(all_data)} rows from {pdf_path}!"
                        )
                    else:
                        print(
                            "No additional data extracted. Check 'pdf_extraction.log' for details."
                        )
                except KeyboardInterrupt:
                    logging.warning("KeyboardInterrupt detected - terminating pool...")
                    pool.terminate()
                    pool.join()
                    raise  # Re-raise to exit
                except Exception as e:
                    logging.error(
                        f"Unexpected error during processing: {str(e)} - terminating pool..."
                    )
                    pool.terminate()
                    pool.join()
                    raise
                finally:
                    pool.close()
                    pool.join()
                    gc.collect()
                    logging.info("Pool closed and resources cleaned up.")
        except Exception as e:
            logging.error(f"Error processing {pdf_path}: {str(e)}")
            print(f"Error processing {pdf_path}: {str(e)}")
            continue
        file_index += 1  # Increment for next file


if __name__ == "__main__":
    main()