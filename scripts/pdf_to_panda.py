import pandas as pd
import tabula

input_file = '../input/first_page_output.pdf'

print("Attempting table extraction with different modes...\n")

# Try default 'guess' mode (what you had before)
try:
    pages_guess = tabula.read_pdf(input_file, pages='1', guess=True)
    print("Guess mode results:")
    if pages_guess:
        df_guess = pages_guess[0] if len(pages_guess) > 1 else pages_guess
        print(f"Number of tables found: {len(pages_guess)}")
        print(f"Shape: {df_guess.shape}")
        print(df_guess.head())  # Show first few rows (even if empty)
    else:
        print("No tables found in guess mode.")
    print("\n" + "="*50 + "\n")
except Exception as e:
    print(f"Guess mode error: {e}")

# Try 'lattice' mode (for tables with visible borders/lines)
try:
    pages_lattice = tabula.read_pdf(input_file, pages='1', lattice=True)
    print("Lattice mode results:")
    if pages_lattice:
        df_lattice = pages_lattice[0] if len(pages_lattice) > 1 else pages_lattice
        print(f"Number of tables found: {len(pages_lattice)}")
        print(f"Shape: {df_lattice.shape}")
        print(df_lattice.head())
    else:
        print("No tables found in lattice mode.")
    print("\n" + "="*50 + "\n")
except Exception as e:
    print(f"Lattice mode error: {e}")

# Try 'stream' mode (for borderless tables with whitespace alignment)
try:
    pages_stream = tabula.read_pdf(input_file, pages='1', stream=True)
    print("Stream mode results:")
    if pages_stream:
        df_stream = pages_stream[0] if len(pages_stream) > 1 else pages_stream
        print(f"Number of tables found: {len(pages_stream)}")
        print(f"Shape: {df_stream.shape}")
        print(df_stream.head())
    else:
        print("No tables found in stream mode.")
    print("\n" + "="*50 + "\n")
except Exception as e:
    print(f"Stream mode error: {e}")

# If all table extractions fail or are empty, dump raw text from the page for inspection
print("Raw text extraction (for reference):")
try:
    # Use tabula's text extraction as a fallback
    text = tabula.read_pdf(input_file, pages='1', output_format='text')
    print(text)
except Exception as e:
    print(f"Text extraction error: {e}")
    # If tabula text fails, suggest installing pdfplumber for better text handling
    print("\nTip: For better raw text, install pdfplumber (pip install pdfplumber) and add:\n")
    print("import pdfplumber\nwith pdfplumber.open(input_file) as pdf:\n    page = pdf.pages[0]\n    print(page.extract_text())")