"""Extract and clean text from PDF and DOCX documents.

The public ``load_document`` function validates the input, dispatches by file
extension, and returns normalized text with paragraph boundaries represented by
one blank line. Extraction failures are exposed as domain-specific exceptions
so CLI code can show useful messages without leaking library internals.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from pathlib import Path
from zipfile import BadZipFile

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table
from docx.text.paragraph import Paragraph
from lxml.etree import XMLSyntaxError
from pypdf import PdfReader
from pypdf.errors import PdfReadError


SUPPORTED_EXTENSIONS = frozenset({".pdf", ".docx"})
_PARAGRAPH_BREAK = re.compile(r"\n[\t ]*\n+")
_HORIZONTAL_WHITESPACE = re.compile(r"[\t\f\v ]+")
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class DocumentLoadError(RuntimeError):
    """Base class for expected document loading failures."""


class UnsupportedDocumentTypeError(DocumentLoadError):
    """Raised when a document is not a supported PDF or DOCX file."""


class DocumentExtractionError(DocumentLoadError):
    """Raised when a supported document cannot yield usable text."""


def clean_text(text: str) -> str:
    """Normalize extracted text while preserving paragraph boundaries.

    PDF extractors commonly produce hard line wraps, non-breaking spaces, and
    line wraps. Single line breaks are therefore treated as wraps,
    while blank lines remain paragraph separators.
    """

    normalized = unicodedata.normalize("NFC", text)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.replace("\u00a0", " ")
    normalized = _CONTROL_CHARACTERS.sub("", normalized)

    paragraphs: list[str] = []
    for block in _PARAGRAPH_BREAK.split(normalized):
        lines = []
        for line in block.split("\n"):
            cleaned_line = _HORIZONTAL_WHITESPACE.sub(" ", line).strip()
            if cleaned_line:
                lines.append(cleaned_line)
        if lines:
            paragraphs.append(" ".join(lines))

    return "\n\n".join(paragraphs)


def _join_paragraphs(paragraphs: Iterable[str]) -> str:
    cleaned = [clean_text(paragraph) for paragraph in paragraphs]
    return "\n\n".join(paragraph for paragraph in cleaned if paragraph)


def _extract_pdf(path: Path) -> str:
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            try:
                unlocked = reader.decrypt("")
            except Exception as exc:  # pypdf exposes multiple crypto errors
                raise DocumentExtractionError(
                    f"PDF '{path.name}' is encrypted and cannot be opened."
                ) from exc
            if not unlocked:
                raise DocumentExtractionError(
                    f"PDF '{path.name}' is encrypted and requires a password."
                )

        page_text = []
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                extracted = page.extract_text() or ""
            except Exception as exc:
                raise DocumentExtractionError(
                    f"Could not extract text from page {page_number} of '{path.name}'."
                ) from exc
            cleaned = clean_text(extracted)
            if cleaned:
                page_text.append(cleaned)
    except DocumentExtractionError:
        raise
    except (OSError, PdfReadError, ValueError) as exc:
        raise DocumentExtractionError(
            f"Could not read PDF '{path.name}'. The file may be damaged."
        ) from exc

    return "\n\n".join(page_text)


def _extract_docx(path: Path) -> str:
    try:
        document = Document(path)
    except (OSError, BadZipFile, PackageNotFoundError, ValueError, KeyError, XMLSyntaxError) as exc:
        raise DocumentExtractionError(
            f"Could not read DOCX '{path.name}'. The file may be damaged."
        ) from exc

    paragraphs: list[str] = []
    for block in document.iter_inner_content():
        if isinstance(block, Paragraph):
            paragraphs.append(block.text)
            continue
        if isinstance(block, Table):
            # Rows remain separate paragraphs and cells remain visibly
            # separated. Merged cells are identified by their underlying XML
            # element, rather than by text (distinct cells can have equal text).
            for row in block.rows:
                cells: list[str] = []
                seen_cells: set[object] = set()
                for cell in row.cells:
                    if cell._tc in seen_cells:
                        continue
                    seen_cells.add(cell._tc)
                    cell_text = clean_text(cell.text)
                    if cell_text:
                        cells.append(cell_text)
                if cells:
                    paragraphs.append(" | ".join(cells))

    return _join_paragraphs(paragraphs)


def load_document(file_path: str | Path) -> str:
    """Load a PDF or DOCX file and return clean, non-empty text.

    Args:
        file_path: Path to a local ``.pdf`` or ``.docx`` file.

    Raises:
        DocumentLoadError: If the path is invalid, unsupported, damaged,
            encrypted, or contains no extractable text.
    """

    path = Path(file_path).expanduser()
    if not path.exists():
        raise DocumentLoadError(f"Document not found: '{path}'.")
    if not path.is_file():
        raise DocumentLoadError(f"Document path is not a file: '{path}'.")

    extension = path.suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise UnsupportedDocumentTypeError(
            f"Unsupported document type '{extension or '(none)'}'. "
            f"Supported types: {supported}."
        )

    text = _extract_pdf(path) if extension == ".pdf" else _extract_docx(path)
    if not text.strip():
        raise DocumentExtractionError(
            f"No extractable text was found in '{path.name}'. "
            "The document may be empty or image-only."
        )
    return text
