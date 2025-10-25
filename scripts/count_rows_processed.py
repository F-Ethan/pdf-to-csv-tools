import os
import pandas as pd


# Example usage:
directory_to_scan = "../../../Processed/"  # Replace with your desired path


def get_csv_row_count(filepath):
    """
    Counts the number of data rows in a CSV file (excluding the header).
    """
    try:
        df = pd.read_csv(filepath)
        return len(df)
    except FileNotFoundError:
        print(f"Error: CSV file not found at {filepath}")
        return None
    except Exception as e:
        print(f"An error occurred while reading the CSV file: {e}")
        return None

def get_folders_in_directory(path):
    """
    Returns a list of folder names within the specified path.
    """
    folders = []
    for item in os.listdir(path):
        item_path = os.path.join(path, item)
        if os.path.isdir(item_path):
            folders.append(item)
    return folders

if __name__ == "__main__":


    folder_list = get_folders_in_directory(directory_to_scan)
    # print(f"Folders in '{directory_to_scan}': {folder_list}")

    for folder in folder_list:
        files = [
            os.path.join(folder, f)
        for f in folder
        ]
        print(folder)
        print(files)

        processed_files_totals = []

        # Example usage:
        for file in files:
            if file.lower().endswith(".csv"):
                row_count_csv = get_csv_row_count(file)
                data = [file, row_count_csv]
                if row_count_csv is not None:
                    print(f"Number of data rows in CSV: {row_count_csv}")

            elif file.lower().endswith(".xlsx"):
                row_count_xlsx = get_xlsx_row_count(file)
                data = [file,row_count_xlsx]
                if row_count_xlsx is not None:
                    print(f"Number of data rows in XLSX: {row_count_xlsx}")

                    
