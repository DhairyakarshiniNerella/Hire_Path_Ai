import os
from pypdf import PdfReader
from docx import Document


def extract_text_from_pdf(file_path):
    """Reads a PDF file and returns all its text as one string."""
    reader = PdfReader(file_path)
    text_parts = []
    for page in reader.pages:
        text_parts.append(page.extract_text() or "")
    return "\n".join(text_parts)


def extract_text_from_docx(file_path):
    """Reads a DOCX file and returns all its text as one string."""
    document = Document(file_path)
    text_parts = [paragraph.text for paragraph in document.paragraphs]
    return "\n".join(text_parts)


def extract_resume_text(file_path):
    """
    Detects the file type from its extension and extracts the text.
    Returns a dict: {"success": True, "text": "..."} or {"success": False, "error": "..."}
    """
    if not os.path.exists(file_path):
        return {"success": False, "error": "File not found"}

    extension = file_path.rsplit(".", 1)[-1].lower()

    try:
        if extension == "pdf":
            text = extract_text_from_pdf(file_path)
        elif extension == "docx":
            text = extract_text_from_docx(file_path)
        else:
            return {"success": False, "error": "Unsupported file type"}

        # Clean up extra whitespace
        text = text.strip()

        if not text:
            return {"success": False, "error": "No readable text found in the file"}

        return {"success": True, "text": text}

    except Exception as e:
        # Catches corrupted files, password-protected files, etc.
        return {"success": False, "error": f"Could not read file: {str(e)}"}
