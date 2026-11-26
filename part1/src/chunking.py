"""Deterministic fixed-size, sentence, and paragraph chunking strategies."""

from __future__ import annotations

import re
from enum import StrEnum
from functools import lru_cache

from nltk.tokenize.punkt import PunktTokenizer


DEFAULT_FIXED_SIZE = 1_000
DEFAULT_OVERLAP = 200
_PARAGRAPH_BREAK = re.compile(r"\n[\t ]*\n+")


class ChunkingStrategy(StrEnum):
    """Supported document chunking strategies."""

    FIXED = "fixed"
    SENTENCE = "sentence"
    PARAGRAPH = "paragraph"


class ChunkingError(ValueError):
    """Raised when a chunking request is invalid."""


@lru_cache(maxsize=1)
def _sentence_tokenizer() -> PunktTokenizer:
    """Load NLTK's trained English Punkt model installed during setup."""
    try:
        return PunktTokenizer("english")
    except LookupError as exc:
        raise ChunkingError(
            "NLTK punkt_tab is missing. Install it with: "
            "python -m nltk.downloader -d .venv/nltk_data punkt_tab"
        ) from exc


def _prepare_text(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def fixed_chunks(
    text: str,
    *,
    chunk_size: int = DEFAULT_FIXED_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[str]:
    """Split text into character windows with an exact adjacent overlap."""

    if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or chunk_size < 1:
        raise ChunkingError("chunk_size must be a positive integer")
    if isinstance(overlap, bool) or not isinstance(overlap, int) or overlap < 0:
        raise ChunkingError("overlap must be a non-negative integer")
    if overlap >= chunk_size:
        raise ChunkingError("overlap must be smaller than chunk_size")

    prepared = _prepare_text(text)
    if not prepared:
        return []

    chunks: list[str] = []
    step = chunk_size - overlap
    for start in range(0, len(prepared), step):
        chunk = prepared[start : start + chunk_size]
        if chunk:
            chunks.append(chunk)
        if start + chunk_size >= len(prepared):
            break
    return chunks


def sentence_chunks(text: str) -> list[str]:
    """Return one non-empty Punkt sentence per chunk."""

    prepared = _prepare_text(text)
    if not prepared:
        return []
    return [
        sentence.strip()
        for sentence in _sentence_tokenizer().tokenize(prepared)
        if sentence.strip()
    ]


def paragraph_chunks(text: str) -> list[str]:
    """Return one non-empty blank-line-delimited paragraph per chunk."""

    prepared = _prepare_text(text)
    if not prepared:
        return []
    return [paragraph.strip() for paragraph in _PARAGRAPH_BREAK.split(prepared) if paragraph.strip()]


def chunk_text(
    text: str,
    strategy: str | ChunkingStrategy,
    *,
    chunk_size: int = DEFAULT_FIXED_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[str]:
    """Chunk text using one of the approved strategies.

    Fixed-size options are accepted for a uniform call signature but are used
    only by the ``fixed`` strategy.
    """

    try:
        selected = ChunkingStrategy(strategy)
    except (TypeError, ValueError) as exc:
        choices = ", ".join(item.value for item in ChunkingStrategy)
        raise ChunkingError(
            f"Unknown chunking strategy '{strategy}'. Choose one of: {choices}."
        ) from exc

    if selected is ChunkingStrategy.FIXED:
        return fixed_chunks(text, chunk_size=chunk_size, overlap=overlap)
    if selected is ChunkingStrategy.SENTENCE:
        return sentence_chunks(text)
    return paragraph_chunks(text)
