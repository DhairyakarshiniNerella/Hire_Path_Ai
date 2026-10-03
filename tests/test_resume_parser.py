import os
from docx import Document
from pypdf import PdfWriter
from app.tools.resume_parser import (
    extract_resume_text,
    extract_text_from_docx,
    extract_text_from_pdf,
)


def test_missing_file_returns_error():
    # There is no file at this path, so it should fail gracefully
    result = extract_resume_text("this_file_does_not_exist.pdf")
    assert result["success"] is False
    assert "not found" in result["error"].lower()


def test_unsupported_file_type_returns_error(tmp_path):
    # tmp_path is a temporary folder pytest creates and deletes automatically
    fake_file = tmp_path / "resume.txt"
    fake_file.write_text("Some resume content")

    result = extract_resume_text(str(fake_file))
    assert result["success"] is False
    assert "unsupported" in result["error"].lower()


def test_docx_extraction_returns_text(tmp_path):
    # Create a real, temporary .docx file to test against
    docx_path = tmp_path / "resume.docx"
    document = Document()
    document.add_paragraph("Jane Doe")
    document.add_paragraph("Email: jane.doe@example.com")
    document.add_paragraph("Skills: Python, SQL, Machine Learning")
    document.save(str(docx_path))

    result = extract_resume_text(str(docx_path))

    assert result["success"] is True
    assert "Jane Doe" in result["text"]
    assert "Python" in result["text"]


def test_pdf_extension_is_routed_to_pdf_extractor(tmp_path):
    # A blank PDF has no extractable text, so this should hit the
    # "No readable text found" branch rather than the docx path.
    pdf_path = tmp_path / "resume.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with open(pdf_path, "wb") as f:
        writer.write(f)

    result = extract_resume_text(str(pdf_path))

    assert result["success"] is False
    assert "no readable text" in result["error"].lower()


def test_extension_matching_is_case_insensitive(tmp_path):
    docx_path = tmp_path / "resume.DOCX"
    document = Document()
    document.add_paragraph("John Smith")
    document.save(str(docx_path))

    result = extract_resume_text(str(docx_path))

    assert result["success"] is True
    assert "John Smith" in result["text"]


def test_empty_docx_returns_no_readable_text_error(tmp_path):
    docx_path = tmp_path / "empty.docx"
    Document().save(str(docx_path))

    result = extract_resume_text(str(docx_path))

    assert result["success"] is False
    assert "no readable text" in result["error"].lower()


def test_corrupted_docx_returns_could_not_read_error(tmp_path):
    fake_path = tmp_path / "corrupted.docx"
    fake_path.write_bytes(b"not a real docx file at all")

    result = extract_resume_text(str(fake_path))

    assert result["success"] is False
    assert "could not read file" in result["error"].lower()


def test_directory_traversal_style_path_without_extension_is_unsupported(tmp_path):
    no_ext_path = tmp_path / "resume"
    no_ext_path.write_text("some content")

    result = extract_resume_text(str(no_ext_path))

    assert result["success"] is False
    assert "unsupported" in result["error"].lower()


def test_extract_text_from_docx_joins_paragraphs_with_newlines(tmp_path):
    docx_path = tmp_path / "resume.docx"
    document = Document()
    document.add_paragraph("Line one")
    document.add_paragraph("Line two")
    document.save(str(docx_path))

    text = extract_text_from_docx(str(docx_path))

    assert text == "Line one\nLine two"


def test_extract_text_from_pdf_returns_empty_string_for_blank_page(tmp_path):
    pdf_path = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with open(pdf_path, "wb") as f:
        writer.write(f)

    text = extract_text_from_pdf(str(pdf_path))

    assert text.strip() == ""
