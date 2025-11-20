"""
Document Parser Module

Extracts text content from various document formats including PDF, RTF, and DOCX.
"""

import os
from pathlib import Path
from typing import List, Tuple

def extract_pages_any(file_path: Path) -> List[Tuple[int, str]]:
    """
    Extract text content from various document formats.

    Returns:
        List of (page_number, content) tuples
    """
    file_path = Path(file_path)
    extension = file_path.suffix.lower()

    if extension == '.pdf':
        return extract_pdf_pages(file_path)
    elif extension == '.rtf':
        return extract_rtf_pages(file_path)
    elif extension in ['.docx', '.doc']:
        return extract_docx_pages(file_path)
    elif extension in ['.txt', '.md']:
        return extract_text_pages(file_path)
    else:
        raise ValueError(f"Unsupported file format: {extension}")

def extract_pdf_pages(file_path: Path) -> List[Tuple[int, str]]:
    """Extract text from PDF files."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(file_path)
        pages = []
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text = page.get_text()
            pages.append((page_num + 1, text))
        doc.close()
        return pages
    except ImportError:
        raise ImportError("PyMuPDF is required for PDF processing. Install with: pip install PyMuPDF")

def extract_rtf_pages(file_path: Path) -> List[Tuple[int, str]]:
    """Extract text from RTF files."""
    try:
        from striprtf.striprtf import rtf_to_text
        with open(file_path, 'r', encoding='utf-8') as f:
            rtf_content = f.read()
        text = rtf_to_text(rtf_content)
        return [(1, text)]  # RTF is typically single page
    except ImportError:
        raise ImportError("striprtf is required for RTF processing. Install with: pip install striprtf")

def extract_docx_pages(file_path: Path) -> List[Tuple[int, str]]:
    """Extract text from DOCX files."""
    try:
        from docx import Document
        doc = Document(file_path)
        text_parts = []
        for paragraph in doc.paragraphs:
            text_parts.append(paragraph.text)
        full_text = '\n'.join(text_parts)
        return [(1, full_text)]  # DOCX is typically treated as single page
    except ImportError:
        raise ImportError("python-docx is required for DOCX processing. Install with: pip install python-docx")

def extract_text_pages(file_path: Path) -> List[Tuple[int, str]]:
    """Extract text from plain text files."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    return [(1, content)]