import pandas as pd

# Path to your existing CSV
input_csv = "2012_Primary_Official_Cumalitive.csv"  # Replace with your CSV's path
output_csv = "2012_Primary_Official_Cumalitive_fixed.csv"

# Read the CSV
df = pd.read_csv(input_csv)

# Initialize new columns if not present
for col in ["Cast Votes", "Cast %", "Over Votes", "Over %", "Under Votes", "Under %"]:
    if col not in df.columns:
        df[col] = ""

# Initialize variables
current_office = ""
current_party = ""
candidate_array = []
meta_data = {}

# Process rows
for index, row in df.iterrows():
    candidate = str(row["Candidate"])
    office = row["Office"]
    
    # Update current office
    if office != current_office:
        current_office = office
        meta_data[current_office] = {}
    
    # Determine party
    if candidate.startswith(("REP ", "DEM ", "LIB ", "ACP ")):
        current_party = candidate[:3]
        candidate = candidate[4:].strip()
        df.at[index, "Party"] = current_party
        df.at[index, "Candidate"] = candidate
    elif candidate in ["No Candidate for Race", "No Candidate"]:
        df.at[index, "Party"] = current_party
    else:
        df.at[index, "Party"] = current_party
    
    # Collect candidates or process meta candidates
    if candidate in ["Cast Votes", "Over Votes", "Under Votes"]:
        vote_type = candidate
        votes = str(row["Total Votes"]).replace(",", "")
        percent = row["Total %"]
        
        # Store meta data
        if current_party not in meta_data[current_office]:
            meta_data[current_office][current_party] = {}
        meta_data[current_office][current_party][vote_type] = votes
        meta_data[current_office][current_party][f"{vote_type} %"] = percent
        
        # Assign meta data when Under Votes is reached
        if candidate == "Under Votes" and candidate_array:
            for idx in candidate_array:
                key = (current_office, df.at[idx, "Party"])
                if key in meta_data.get(current_office, {}):
                    df.at[idx, "Cast Votes"] = meta_data[current_office][df.at[idx, "Party"]].get("Cast Votes", "0")
                    df.at[idx, "Cast %"] = meta_data[current_office][df.at[idx, "Party"]].get("Cast Votes %", "0.00%")
                    df.at[idx, "Over Votes"] = meta_data[current_office][df.at[idx, "Party"]].get("Over Votes", "0")
                    df.at[idx, "Over %"] = meta_data[current_office][df.at[idx, "Party"]].get("Over Votes %", "0.00%")
                    df.at[idx, "Under Votes"] = meta_data[current_office][df.at[idx, "Party"]].get("Under Votes", "0")
                    df.at[idx, "Under %"] = meta_data[current_office][df.at[idx, "Party"]].get("Under Votes %", "0.00%")
            candidate_array.clear()
    else:
        # Add candidate to array
        candidate_array.append(index)

# Remove meta candidate rows and duplicates
df = df[~df["Candidate"].isin(["Cast Votes", "Over Votes", "Under Votes"])]
df = df.drop_duplicates(subset=["Office", "Party", "Candidate", "Early Votes", "Total Votes"], keep="first")

# Save to new CSV
df.to_csv(output_csv, index=False)
print(f"Corrected CSV file '{output_csv}' created successfully!")