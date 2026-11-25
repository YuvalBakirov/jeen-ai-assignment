from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

import src.document_loader as document_loader
from src.document_loader import (
    DocumentExtractionError,
    DocumentLoadError,
    UnsupportedDocumentTypeError,
    clean_text,
    load_document,
)


def test_clean_text_normalizes_whitespace_and_preserves_paragraphs() -> None:
    raw = "  First   line\r\ncontinues here.\r\n\r\n Second\tparagraph.  "

    assert clean_text(raw) == "First line continues here.\n\nSecond paragraph."


def test_clean_text_preserves_ambiguous_hyphens() -> None:
    assert clean_text("state-of-\nthe-art") == "state-of- the-art"


def test_clean_text_removes_control_characters_and_nbsp() -> None:
    assert clean_text("safe\x00 text\u00a0here") == "safe text here"


def test_missing_document_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(DocumentLoadError, match="Document not found"):
        load_document(tmp_path / "missing.pdf")


def test_directory_path_is_rejected(tmp_path: Path) -> None:
    directory = tmp_path / "document.pdf"
    directory.mkdir()

    with pytest.raises(DocumentLoadError, match="not a file"):
        load_document(directory)


@pytest.mark.parametrize("filename", ["notes.txt", "document", "archive.doc"])
def test_unsupported_document_type_is_rejected(tmp_path: Path, filename: str) -> None:
    path = tmp_path / filename
    path.write_text("content", encoding="utf-8")

    with pytest.raises(UnsupportedDocumentTypeError, match="Supported types"):
        load_document(path)


def test_docx_extraction_preserves_paragraph_boundaries(tmp_path: Path) -> None:
    path = tmp_path / "sample.docx"
    document = Document()
    document.add_paragraph(" First   paragraph. ")
    document.add_paragraph("")
    document.add_paragraph("Second paragraph.")
    document.save(path)

    assert load_document(path) == "First paragraph.\n\nSecond paragraph."


def test_docx_extraction_includes_table_rows(tmp_path: Path) -> None:
    path = tmp_path / "table.docx"
    document = Document()
    document.add_paragraph("Summary")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Name"
    table.cell(0, 1).text = "Value"
    document.add_paragraph("After table")
    document.save(path)

    assert load_document(path) == "Summary\n\nName | Value\n\nAfter table"


def test_docx_extension_is_case_insensitive(tmp_path: Path) -> None:
    path = tmp_path / "SAMPLE.DOCX"
    document = Document()
    document.add_paragraph("Text")
    document.save(path)

    assert load_document(path) == "Text"


def test_damaged_docx_has_domain_error(tmp_path: Path) -> None:
    path = tmp_path / "damaged.docx"
    path.write_bytes(b"not a docx archive")

    with pytest.raises(DocumentExtractionError, match="may be damaged"):
        load_document(path)


def test_pdf_extraction_combines_non_empty_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "sample.pdf"
    path.write_bytes(b"placeholder")

    class Page:
        def __init__(self, text: str | None) -> None:
            self.text = text

        def extract_text(self) -> str | None:
            return self.text

    class Reader:
        is_encrypted = False
        pages = [Page("Page one\nline two"), Page(None), Page("Page three")]

    monkeypatch.setattr(document_loader, "PdfReader", lambda _: Reader())

    assert load_document(path) == "Page one line two\n\nPage three"


def test_password_protected_pdf_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "protected.pdf"
    path.write_bytes(b"placeholder")

    class Reader:
        is_encrypted = True
        pages: list[object] = []

        def decrypt(self, password: str) -> int:
            return 0

    monkeypatch.setattr(document_loader, "PdfReader", lambda _: Reader())

    with pytest.raises(DocumentExtractionError, match="requires a password"):
        load_document(path)


def test_pdf_page_extraction_failure_reports_page_number(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "broken-page.pdf"
    path.write_bytes(b"placeholder")

    class Page:
        def extract_text(self) -> str:
            raise RuntimeError("parser detail")

    class Reader:
        is_encrypted = False
        pages = [Page()]

    monkeypatch.setattr(document_loader, "PdfReader", lambda _: Reader())

    with pytest.raises(DocumentExtractionError, match="page 1"):
        load_document(path)


def test_blank_pdf_reports_no_extractable_text(tmp_path: Path) -> None:
    path = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with path.open("wb") as output:
        writer.write(output)

    with pytest.raises(DocumentExtractionError, match="No extractable text"):
        load_document(path)


def test_damaged_pdf_has_domain_error(tmp_path: Path) -> None:
    path = tmp_path / "damaged.pdf"
    path.write_bytes(b"not a pdf")

    with pytest.raises(DocumentExtractionError, match="may be damaged"):
        load_document(path)


@pytest.mark.parametrize("merged", [False, True])
def test_table_equal_text_is_preserved_unless_cells_are_merged(
    tmp_path: Path, merged: bool
) -> None:
    path = tmp_path / "cells.docx"
    document = Document()
    table = document.add_table(rows=1, cols=2)
    if merged:
        table.cell(0, 0).merge(table.cell(0, 1)).text = "Same"
    else:
        table.cell(0, 0).text = "Same"
        table.cell(0, 1).text = "Same"
    document.save(path)

    assert load_document(path) == ("Same" if merged else "Same | Same")


def test_real_pdf_text_extraction(tmp_path: Path) -> None:
    """Exercise pypdf's actual text parser rather than a mocked reader."""
    path = tmp_path / "text.pdf"
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})
    })
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 72 720 Td (Document retrieval works.) Tj ET")
    page[NameObject("/Contents")] = stream
    writer.write(path)

    assert load_document(path) == "Document retrieval works."
