
import argparse
import os
from pathlib import Path
import logging

from .document_parser import extract_pages_any
from .chunking import clean_text

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def preprocess_document(input_path: Path, output_dir: Path):
    """Extracts content from a document and saves it as a clean Markdown file."""
    try:
        logging.info(f"Processing file: {input_path.name}")
        # Extract text content from the document
        pages = extract_pages_any(input_path)
        full_text = "\n\n".join([content for page_num, content in pages])
        
        # Clean the extracted text
        cleaned = clean_text(full_text)
        
        # Define the output path for the Markdown file
        output_filename = input_path.stem + ".md"
        output_path = output_dir / output_filename
        
        # Write the cleaned content to the Markdown file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(cleaned)
        logging.info(f"Successfully created {output_path}")
        
    except Exception as e:
        logging.error(f"Failed to process {input_path.name}: {e}", exc_info=True)

def main():
    ap = argparse.ArgumentParser(description="Preprocess various document formats into clean Markdown files.")
    ap.add_argument("--input_dir", default="./documents", help="Directory containing the source documents (PDF, RTF, etc.).")
    ap.add_argument("--output_dir", default="./processed_md", help="Directory to save the processed Markdown files.")
    args = ap.parse_args()

    input_path = Path(args.input_dir)
    output_path = Path(args.output_dir)

    if not input_path.is_dir():
        raise SystemExit(f"Error: Input directory not found at '{input_path}'")

    # Create the output directory if it doesn't exist
    output_path.mkdir(exist_ok=True)

    logging.info(f"Starting preprocessing from '{input_path}' to '{output_path}'.")

    # Process each file in the input directory
    for doc_file in sorted(input_path.glob('*')):
        if doc_file.is_file() and not doc_file.name.startswith('.'):
            preprocess_document(doc_file, output_path)

    logging.info("Preprocessing complete.")

if __name__ == "__main__":
    # This allows the script to be run with `python -m rag_system.preprocess`
    # assuming the script is saved as rag_system/preprocess.py
    main()
