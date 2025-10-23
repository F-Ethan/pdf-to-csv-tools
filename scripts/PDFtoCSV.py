
import pdfplumber
import pandas as pd
import re

# Path to your PDF file
pdf_path = "2012 Primary Official cumulative.pdf"  # Replace with your PDF file path
output_csv = "2012_Primary_Official_Cumalitive.csv"     # Output Excel file name

# Initialize lists and dictionaries
data = []
candidate_array = []
meta_data = {}

# Regular expressions
candidate_pattern = re.compile(r"^(REP|DEM|LIB|ACP)\s+(.*?)\s+(\d+,?\d*)\s+(\d+\.\d{2}%)\s+(\d+,?\d*)\s+(\d+\.\d{2}%)\s+(\d+,?\d*)\s+(\d+\.\d{2}%)")
votes_pattern = re.compile(r"^(Cast Votes|Over Votes|Under Votes):\s*(\d+,?\d*)\s+(\d+\.\d{2}%)\s+(\d+,?\d*)\s+(\d+\.\d{2}%)\s+(\d+,?\d*)\s+(\d+\.\d{2}%)")

# Open the PDF
with pdfplumber.open(pdf_path) as pdf:
    current_office = ""
    full_office = ""
    current_party = "N/A"
    
    for page in pdf.pages:
        text = page.extract_text()
        if not text:
            continue
        lines = text.split("\n")
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Detect office
            if ", Vote For 1" in line:
                current_office = line.split(", Vote For")[0].strip()
                meta_data[current_office] = { }
                candidate_array.clear()  # Clear array when a new office starts
                print(f"Detected office: {current_office}")
                continue
                
            # Match candidate lines
            candidate_match = candidate_pattern.match(line)
            if candidate_match:
                party = candidate_match.group(1)  # Extract party (e.g., REP, DEM)
                current_party = party  # Update current_party for meta data
                candidate = candidate_match.group(2).strip()
                early_votes = candidate_match.group(3).replace(",", "")
                early_percent = candidate_match.group(4)
                election_votes = candidate_match.group(5).replace(",", "")
                election_percent = candidate_match.group(6)
                total_votes = candidate_match.group(7).replace(",", "")
                total_percent = candidate_match.group(8)
                
                # Ensure party is in meta_data
                if current_party not in meta_data[current_office]:
                    meta_data[current_office][current_party] = {}
                
                # Store candidate data in array
                candidate_array.append({
                    "Office": current_office,
                    "Party": party,
                    "Candidate": candidate,
                    "Early Votes": early_votes,
                    "Early %": early_percent,
                    "Election Votes": election_votes,
                    "Election %": election_percent,
                    "Total Votes": total_votes,
                    "Total %": total_percent,
                    "Cast Votes": "",
                    "Cast %": "",
                    "Over Votes": "",
                    "Over %": "",
                    "Under Votes": "",
                    "Under %": ""
                })
                
            # Match Cast/Over/Under Votes
            votes_match = votes_pattern.match(line)
            if votes_match:
                if not current_party:
                    print(f"Warning: No party identified for meta data line: {line}")
                    continue
                vote_type = votes_match.group(1)
                votes = votes_match.group(2).replace(",", "")
                percent = votes_match.group(3)
                
                # Store meta data
                meta_data[current_office][current_party][vote_type] = votes
                meta_data[current_office][current_party][f"{vote_type} %"] = percent
                
                # Assign meta data when Under Votes is reached
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
                
            # Handle "No Candidate for Race"
            if "No Candidate for Race" in line:
                if not current_party:
                    print(f"Warning: No party identified for No Candidate line: {line}")
                    continue
                candidate_array.append({
                    "Office": current_office,
                    "Party": current_party,
                    "Candidate": "No Candidate",
                    "Early Votes": "0",
                    "Early %": "0.00%",
                    "Election Votes": "0",
                    "Election %": "0.00%",
                    "Total Votes": "0",
                    "Total %": "0.00%",
                    "Cast Votes": "",
                    "Cast %": "",
                    "Over Votes": "",
                    "Over %": "",
                    "Under Votes": "",
                    "Under %": ""
                })

# Create DataFrame and save to CSV
if data:
    df = pd.DataFrame(data)
    df = df.drop_duplicates(subset=["Office", "Party", "Candidate", "Early Votes", "Total Votes"], keep="first")
    df.to_csv(output_csv, index=False)
    print(f"CSV file '{output_csv}' created successfully!")
else:
    print("No data extracted from the PDF.")