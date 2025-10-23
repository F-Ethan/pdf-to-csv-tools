import PyPDF2

def extract_first_page(input_pdf_path, output_pdf_path):
    try:
        # Open the input PDF file
        with open(input_pdf_path, 'rb') as input_file:
            reader = PyPDF2.PdfReader(input_file)
            
            # Create a PDF writer object
            writer = PyPDF2.PdfWriter()
            
            # Add the first page to the writer
            writer.add_page(reader.pages[0])
            
            # Write the first page to the output PDF
            with open(output_pdf_path, 'wb') as output_file:
                writer.write(output_file)
                
            print(f"First page extracted successfully to {output_pdf_path}")
            
            # Print basic information about the first page
            print("\nPage 1 Information:")
            print(f"Page size: {reader.pages[0].mediabox}")
            print(f"Text content sample (first 200 characters):")
            text = reader.pages[0].extract_text()[:200]
            print(text)
            
    except FileNotFoundError:
        print(f"Error: Input file {input_pdf_path} not found")
    except Exception as e:
        print(f"Error: {str(e)}")

# Example usage
if __name__ == "__main__":
    input_path = "../input/Tarrant_May-04-2019_Joint_General_Special_Elections_Precinct_Results.pdf"  # Replace with your input PDF path
    output_path = "../output/first_page_output.pdf"  # Output file name
    extract_first_page(input_path, output_path)