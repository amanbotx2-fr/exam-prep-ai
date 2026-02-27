"""
ExamAI — File Processor Utility
Extracts plain text from PDF, DOCX, TXT, and image files.
"""

import os
import tempfile

from langchain.document_loaders import PyPDFLoader
from docx import Document as DocxDocument
from PIL import Image
import pytesseract


# ── Supported extensions ──
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg"}


def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from a PDF file using PyPDFLoader."""
    loader = PyPDFLoader(file_path)
    documents = loader.load()
    return "\n".join(doc.page_content for doc in documents)


def extract_text_from_docx(file_path: str) -> str:
    """Extract text from a DOCX file using python-docx."""
    doc = DocxDocument(file_path)
    return "\n".join(para.text for para in doc.paragraphs if para.text.strip())


def extract_text_from_txt(file_path: str) -> str:
    """Extract text from a plain text file."""
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def extract_text_from_image(file_path: str) -> str:
    """Extract text from an image file using pytesseract OCR."""
    image = Image.open(file_path)
    text = pytesseract.image_to_string(image)
    return text.strip()


def extract_text(file_path: str) -> str:
    """
    Dispatcher: detect file type by extension and extract text.
    Raises ValueError for unsupported types.
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    elif ext == ".docx":
        return extract_text_from_docx(file_path)
    elif ext == ".txt":
        return extract_text_from_txt(file_path)
    elif ext in (".png", ".jpg", ".jpeg"):
        return extract_text_from_image(file_path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")
