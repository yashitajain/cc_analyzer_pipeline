"""
PDF text extraction service using pdfplumber.
"""

import pdfplumber
import hashlib
from io import BytesIO


async def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """
    Extract text from PDF bytes.

    Args:
        pdf_bytes: Raw PDF file content

    Returns:
        Extracted text from all pages

    Raises:
        ValueError: If PDF is invalid
    """
    try:
        pdf_file = BytesIO(pdf_bytes)
        text = ""

        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"

        if not text.strip():
            raise ValueError("No text extracted from PDF")

        return text

    except Exception as e:
        raise ValueError(f"Failed to extract PDF: {str(e)}")


async def get_pdf_hash(pdf_bytes: bytes) -> str:
    """
    Get SHA-256 hash of PDF for deduplication.

    Args:
        pdf_bytes: Raw PDF content

    Returns:
        SHA-256 hash string
    """
    return hashlib.sha256(pdf_bytes).hexdigest()
