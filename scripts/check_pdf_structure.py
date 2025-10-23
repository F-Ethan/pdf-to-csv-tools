import pdfplumber
import logging
import os

# this script checks for the number of tables in a PDF file


# Set up logging
logging.basicConfig(filename='../logs/pdf_structure_debug.log', level=logging.DEBUG, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Paths
input_folder = '../input'
pdf_files = [os.path.join(input_folder, f) for f in os.listdir(input_folder) if f.lower().endswith('.pdf')]
# Path to your PDF

def check_pdf_structure(pdf_files):
    for pdf_path in pdf_files:
        try:
            with pdfplumber.open(pdf_path) as pdf:
                print(f"PDF has {len(pdf.pages)} pages")
                logging.info(f"PDF has {len(pdf.pages)} pages")

                for page_num, page in enumerate(pdf.pages, 1):
                    print(f"\nAnalyzing page {page_num}...")
                    logging.info(f"Analyzing page {page_num}")

                    # Check for text
                    text = page.extract_text()
                    if text:
                        print(f"Page {page_num} contains text (first 200 chars):\n{text[:200]}")
                        logging.debug(f"Page {page_num} text:\n{text}")
                        # Analyze text layout for tabular patterns
                        lines = text.split("\n")
                        line_lengths = [len(line.strip()) for line in lines if line.strip()]
                        if line_lengths:
                            avg_line_length = sum(line_lengths) / len(line_lengths)
                            print(f"Page {page_num} average line length: {avg_line_length:.2f} chars")
                            logging.info(f"Page {page_num} average line length: {avg_line_length:.2f} chars")
                            if any("  " in line for line in lines if line.strip()):  # Check for multiple spaces (common in tables)
                                print(f"Page {page_num} likely contains tabular text (multiple spaces detected)")
                                logging.info(f"Page {page_num} likely contains tabular text (multiple spaces)")
                        else:
                            print(f"Page {page_num} has no text content")
                            logging.warning(f"Page {page_num} has no text content")

                    # Check for tables
                    tables = page.extract_tables({
                        "vertical_strategy": "lines",
                        "horizontal_strategy": "lines",
                        "snap_tolerance": 3,
                        "join_tolerance": 3,
                        "min_words_vertical": 1,
                        "min_words_horizontal": 1
                    })
                    if tables:
                        print(f"Page {page_num} contains {len(tables)} table(s)")
                        logging.info(f"Page {page_num} contains {len(tables)} table(s)")
                        for table_num, table in enumerate(tables, 1):
                            print(f"Table {table_num} has {len(table)} rows and {len(table[0]) if table else 0} columns")
                            logging.debug(f"Table {table_num} on page {page_num}:\n{table}")
                            for row_num, row in enumerate(table, 1):
                                row_text = " ".join([str(cell) for cell in row if cell]).strip()
                                print(f"Table {table_num} row {row_num}: {row_text[:100]}...")
                                logging.debug(f"Table {table_num} row {row_num}: {row_text}")
                    else:
                        print(f"Page {page_num} has no detectable tables")
                        logging.info(f"Page {page_num} has no detectable tables")

                    # Check for visual elements (lines, rectangles) that might indicate tables
                    lines = page.lines
                    rects = page.rects
                    if lines or rects:
                        print(f"Page {page_num} has {len(lines)} lines and {len(rects)} rectangles (possible table borders)")
                        logging.info(f"Page {page_num} has {len(lines)} lines and {len(rects)} rectangles")

        except FileNotFoundError:
            print(f"Error: PDF file not found at {pdf_path}")
            logging.error(f"PDF file not found: {pdf_path}")
            return

if __name__ == "__main__":
    check_pdf_structure(pdf_files)