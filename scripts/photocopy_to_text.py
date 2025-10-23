import os
import shutil
import logging
from pdf2image import convert_from_path
from PIL import Image
import pandas as pd
import re
import io
import numpy as np
import cv2  # For image preprocessing
import pytesseract  # For fallback OCR

# Setup directories and logging
input_dir = '../input'
output_dir = '../output/extracted_tables'
log_dir = '../logs'

# Clear old logs for clarity
if os.path.exists(log_dir):
    shutil.rmtree(log_dir)
os.makedirs(log_dir, exist_ok=True)
os.makedirs(output_dir, exist_ok=True)

# Setup logging
log_file = os.path.join(log_dir, 'extraction.log')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()  # Also log to console
    ]
)
logger = logging.getLogger(__name__)

# Path to your PDF
pdf_path = os.path.join(input_dir, 'Gen Election November 2004 Tracy.pdf')
logger.info(f"Starting extraction from {pdf_path}")
logger.info(f"Output to {output_dir}")
logger.info(f"Logs to {log_file}")

# Toggle img2table (True for advanced detection, False for raw OCR fallback)
use_img2table = True

# Convert PDF to images
try:
    pages = convert_from_path(pdf_path, dpi=300)
    logger.info(f"PDF loaded: {len(pages)} pages")
except Exception as e:
    logger.error(f"Failed to load PDF: {e}")
    raise

for i, page in enumerate(pages):
    logger.info(f"Processing page {i+1}")
    
    # Preprocess: Grayscale + threshold for cleaner OCR on photocopies
    page_np = np.array(page)
    gray = cv2.cvtColor(page_np, cv2.COLOR_RGB2GRAY)
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    page_clean = Image.fromarray(thresh)
    
    tables_extracted = 0
    if use_img2table:
        # Convert cleaned image to BytesIO
        img_bytes = io.BytesIO()
        page_clean.save(img_bytes, format='PNG')
        img_bytes.seek(0)
        
        # img2table with tuned OCR - added implicit_columns and rotation detection
        from img2table.document import Image as Img2TableImage
        from img2table.ocr import TesseractOCR
        
        doc = Img2TableImage(src=img_bytes, detect_rotation=True)  # Detect skew/rotation for scanned docs
        ocr = TesseractOCR(n_threads=1, lang='eng', psm=1)  # Removed oem=1; default works (LSTM via psm)
        tables = doc.extract_tables(
            ocr=ocr, 
            implicit_rows=True, 
            implicit_columns=True,  # Infer columns from content alignment
            borderless_tables=True, 
            min_confidence=30  # Lower for faint scans; increase to 50 if too noisy
        )
        
        if tables:
            for tbl_idx, table in enumerate(tables):
                df = table.df
                if df.empty:
                    logger.warning(f"Page {i+1} (Table {tbl_idx+1}): Empty DataFrame")
                    continue
                
                # Ensure all data is string first
                df = df.astype(str)
                
                # Clean cells: Strip common OCR artifacts and handle merged text
                def clean_cell(val):
                    if pd.isna(val) or val == 'nan':
                        return ''
                    s = str(val).strip()
                    s = re.sub(r'[\|\]\n\[]', '', s)  # Remove | ] \n [
                    s = re.sub(r'\s+', ' ', s)  # Normalize spaces
                    # Split merged contest names in col0 (e.g., "Registered VotersBallots Cast" -> separate if possible)
                    if ',' in s and ' ' not in s.split(',')[0]:  # Rough split for known merges
                        parts = s.split('Ballots Cast')
                        if len(parts) > 1:
                            logger.debug(f"Split merged cell: {s} -> {parts[0]}, Ballots Cast")
                            return parts[0]  # For now, keep first; extend for full split
                    return s
                
                df = df.map(clean_cell)
                
                # Improved header detection: Skip if first row is all numeric or short
                first_row = df.iloc[0] if len(df) > 0 else pd.Series()
                first_row_numeric = first_row.apply(lambda x: bool(re.match(r'^\d+$', str(x)))).all()
                first_row_short = all(len(str(x)) < 5 for x in first_row if x != '')
                if not first_row_numeric and not first_row_short and len(df) > 1:
                    header = df.iloc[0].tolist()
                    # Attempt to split merged headers (e.g., "Cum. Dug jErda G-1 G-2 G-4" -> ['Cum. Dug', 'jErda', 'G-1', 'G-2', 'G-4'])
                    split_header = []
                    for h in header:
                        if len(h.split()) > 1:  # If merged
                            candidates = re.split(r'\s+(?=[A-Z][a-z]+|\d)', h)  # Split before capital or number (rough for precincts)
                            split_header.extend([c.strip() for c in candidates if c.strip()])
                        else:
                            split_header.append(h)
                    if len(split_header) > len(header):
                        logger.info(f"Page {i+1} (Table {tbl_idx+1}): Split merged headers from {len(header)} to {len(split_header)} cols")
                        # Resize df to new cols (pad/truncate data - simplistic; may need adjustment)
                        old_cols = len(header)
                        new_cols = len(split_header)
                        if new_cols > old_cols:
                            # Pad data cols with empty
                            for j in range(old_cols, new_cols):
                                df.insert(j, f'Extra_{j}', '')
                        elif new_cols < old_cols:
                            # Drop extra data cols
                            df = df.iloc[:, :new_cols]
                        header = split_header
                    df = df.iloc[1:].reset_index(drop=True)
                    df.columns = header[:len(df.columns)]  # Ensure no overflow
                    logger.info(f"Page {i+1} (Table {tbl_idx+1}): Header detected ({len(header)} cols)")
                else:
                    df.columns = [f'Precinct_{j}' for j in range(len(df.columns))]  # Default precinct names
                    logger.info(f"Page {i+1} (Table {tbl_idx+1}): No header detected, using precinct defaults ({len(df.columns)} cols)")
                
                # Type cols: Col0 text (group contests/candidates), others numeric
                num_rows_before = len(df)
                if len(df) > 0 and len(df.columns) > 0:
                    df.iloc[:, 0] = df.iloc[:, 0].astype(str)  # Keep contest titles and candidates as text
                
                for j in range(1, len(df.columns)):
                    col_series = df.iloc[:, j]
                    if not col_series.empty:
                        try:
                            numeric_series = pd.to_numeric(col_series, errors='coerce')
                            df.iloc[:, j] = numeric_series.fillna(0).astype(int)
                            logger.debug(f"Page {i+1} (Table {tbl_idx+1}, Col {df.columns[j]}): Converted to numeric")
                        except Exception as te:
                            logger.warning(f"Page {i+1} (Table {tbl_idx+1}, Col {df.columns[j]}): Numeric conversion failed - {te}. Keeping as str.")
                            df.iloc[:, j] = col_series
                
                # Drop truly empty rows (all data cols 0 and col0 empty), but keep contest titles (even if 0s)
                if len(df) > 0:
                    data_cols_mask = df.iloc[:, 1:].eq(0).all(axis=1)  # All data 0?
                    text_empty = df.iloc[:, 0].str.strip() == ''
                    mask = ~(data_cols_mask & text_empty)  # Keep if not (all 0 and empty text)
                    df = df[mask]
                
                num_rows_after = len(df)
                if not df.empty:
                    csv_path = os.path.join(output_dir, f'page_{i+1}_table_{tbl_idx+1}.csv')
                    df.to_csv(csv_path, index=False)
                    logger.info(f"Page {i+1} (Table {tbl_idx+1}): Extracted to {csv_path} ({num_rows_after} rows after cleaning, from {num_rows_before})")
                    tables_extracted += 1
                    logger.debug(f"Sample data:\n{df.head().to_string()}")
                else:
                    logger.warning(f"Page {i+1} (Table {tbl_idx+1}): Empty after cleaning - skipped CSV")
        
        if tables_extracted > 0:
            logger.info(f"Page {i+1}: Successfully extracted {tables_extracted} table(s)")
            continue
        
        logger.warning(f"Page {i+1}: No tables with img2table - falling back to raw OCR")
    
    # Fallback: Raw OCR parsing for better control on structure
    custom_config = r'--oem 1 --psm 6'  # LSTM engine, uniform block for tables
    raw_text = pytesseract.image_to_string(page_clean, config=custom_config)
    
    # Parse raw text into table
    lines = [line.strip() for line in raw_text.split('\n') if line.strip() and len(line) > 10]
    if not lines:
        logger.warning(f"Page {i+1}: No text in fallback")
        continue
    
    # Find header: Line with many short words (precinct names)
    header_line = None
    for line in lines[:5]:  # Assume header early
        words = re.split(r'\s{2,}', line)
        if len(words) > 10:  # Many columns
            header_line = words
            break
    if not header_line:
        header_line = ['Precinct_' + str(j) for j in range(25)]  # Default 25 cols from logs
    
    # Estimate col widths from header
    col_widths = [len(w) for w in header_line]
    
    # Parse data rows
    rows = []
    for line in lines:
        # Split by estimated widths or multiple spaces
        cols = re.split(r'\s{2,}', line.strip())
        if len(cols) < 2:
            continue
        # Pad to header len
        while len(cols) < len(header_line):
            cols.append('')
        cols = cols[:len(header_line)]
        rows.append(cols)
    
    if rows:
        df = pd.DataFrame(rows, columns=header_line)
        # Clean and type as above
        df.iloc[:, 0] = df.iloc[:, 0].astype(str)
        for j in range(1, len(df.columns)):
            df.iloc[:, j] = pd.to_numeric(df.iloc[:, j], errors='coerce').fillna(0).astype(int)
        # Drop empty
        mask = df.iloc[:, 0].str.strip() != ''
        df = df[mask]
        csv_path = os.path.join(output_dir, f'page_{i+1}_fallback.csv')
        df.to_csv(csv_path, index=False)
        logger.info(f"Page {i+1}: Fallback table to {csv_path} ({len(df)} rows)")
        tables_extracted += 1
        logger.debug(f"Fallback sample:\n{df.head().to_string()}")
    else:
        logger.warning(f"Page {i+1}: No data in fallback")
    
    logger.info(f"Page {i+1}: Extracted {tables_extracted} table(s) total")

logger.info("Extraction complete. Check logs/extraction.log for details.")