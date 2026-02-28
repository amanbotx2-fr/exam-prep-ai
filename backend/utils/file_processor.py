"""
ExamAI — File Processor Utility
Extracts plain text from PDF, DOCX, TXT, and image files.
"""

import os
import math

from langchain_community.document_loaders import PyPDFLoader
from docx import Document as DocxDocument
from PIL import Image
import pytesseract


# ── Supported extensions ──
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg"}

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def extract_text_from_pdf(file_path: str):
    """Extract text and real page count from a PDF."""
    loader = PyPDFLoader(file_path)
    documents = loader.load()
    text = "\n".join(doc.page_content for doc in documents)
    return text, len(documents)


def extract_text_from_docx(file_path: str):
    """Extract text from a DOCX file. Estimate pages from word count."""
    doc = DocxDocument(file_path)
    text = "\n".join(para.text for para in doc.paragraphs if para.text.strip())
    pages = max(1, math.ceil(len(text.split()) / 300))
    return text, pages


def extract_text_from_txt(file_path: str):
    """Extract text from a plain text file. Estimate pages from word count."""
    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    pages = max(1, math.ceil(len(text.split()) / 300))
    return text, pages


def extract_text_from_image(file_path: str):
    """Extract text from an image file using pytesseract OCR. Always 1 page."""
    image = Image.open(file_path)
    text = pytesseract.image_to_string(image)
    return text.strip(), 1


def extract_text(file_path: str):
    """
    Dispatcher: detect file type by extension and extract text.
    Returns (text, page_count) tuple.
    Raises ValueError for unsupported types.
    """
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    elif ext == ".docx":
        return extract_text_from_docx(file_path)
    elif ext == ".txt":
        return extract_text_from_txt(file_path)
    elif ext in IMAGE_EXTENSIONS:
        return extract_text_from_image(file_path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")
