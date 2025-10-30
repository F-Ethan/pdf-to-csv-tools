import os
import pandas as pd

# Example usage:
directory_to_scan = "../../../Processed/"  # Replace with your desired path


def get_csv_stats(filepath):
    """
    Counts the number of data rows and non-null cells in a CSV file (excluding the header for rows).
    """
    try:
        df = pd.read_csv(filepath)
        rows = len(df)
        cells = df.count().sum()  # Total non-null values across all columns
        return rows, cells
    except FileNotFoundError:
        print(f"Error: CSV file not found at {filepath}")
        return None, None
    except Exception as e:
        print(f"An error occurred while reading the CSV file: {e}")
        return None, None


def get_xlsx_stats(filepath):
    """
    Counts the number of data rows and non-null cells in an XLSX file (first sheet only).
    """
    try:
        df = pd.read_excel(filepath, sheet_name=0)  # Read the first sheet
        rows = len(df)
        cells = df.count().sum()  # Total non-null values across all columns
        return rows, cells
    except FileNotFoundError:
        print(f"Error: XLSX file not found at {filepath}")
        return None, None
    except Exception as e:
        print(f"An error occurred while reading the XLSX file: {e}")
        return None, None


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

    all_data = []  # Collect data for all files across folders

    for folder in folder_list:
        folder_path = os.path.join(directory_to_scan, folder)
        # Get list of CSV and XLSX files in the folder
        file_list = [
            f for f in os.listdir(folder_path)
            if os.path.isfile(os.path.join(folder_path, f)) and
            f.lower().endswith(('.csv', '.xlsx'))
        ]
        print(f"Folder: {folder}")
        print(f"Files: {file_list}")

        for filename in file_list:
            filepath = os.path.join(folder_path, filename)
            filetype = 'csv' if filename.lower().endswith('.csv') else 'xlsx'
            rows, cells = None, None

            if filetype == 'csv':
                rows, cells = get_csv_stats(filepath)
                if rows is not None:
                    print(f"Number of data rows in CSV '{filename}': {rows}, cells: {cells}")

            elif filetype == 'xlsx':
                rows, cells = get_xlsx_stats(filepath)
                if rows is not None:
                    print(f"Number of data rows in XLSX '{filename}': {rows}, cells: {cells}")

            # Add to data list if successful
            if rows is not None and cells is not None:
                all_data.append({
                    'file_type': filetype,
                    'file_name': filename,
                    'rows': rows,
                    'cells': cells
                })

    # Create output CSV
    if all_data:
        output_df = pd.DataFrame(all_data)
        output_filename = 'file_summary.csv'
        output_df.to_csv(output_filename, index=False)
        print(f"\nSummary saved to '{output_filename}' with {len(all_data)} files processed.")
    else:
        print("No valid files were processed.")