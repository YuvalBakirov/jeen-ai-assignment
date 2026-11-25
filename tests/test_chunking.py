from __future__ import annotations

import pytest

from src.chunking import (
    DEFAULT_FIXED_SIZE,
    DEFAULT_OVERLAP,
    ChunkingError,
    ChunkingStrategy,
    chunk_text,
    fixed_chunks,
    paragraph_chunks,
    sentence_chunks,
)


@pytest.mark.parametrize("chunker", [fixed_chunks, sentence_chunks, paragraph_chunks])
def test_empty_or_whitespace_text_returns_no_chunks(chunker) -> None:
    assert chunker(" \n\t ") == []


def test_fixed_strategy_uses_approved_defaults() -> None:
    text = "x" * 1_801

    chunks = fixed_chunks(text)

    assert DEFAULT_FIXED_SIZE == 1_000
    assert DEFAULT_OVERLAP == 200
    assert [len(chunk) for chunk in chunks] == [1_000, 1_000, 201]
    assert chunks[0][-200:] == chunks[1][:200]
    assert chunks[1][-200:] == chunks[2][:200]


def test_fixed_text_shorter_than_window_is_one_chunk() -> None:
    assert fixed_chunks("short text", chunk_size=20, overlap=5) == ["short text"]


def test_fixed_text_equal_to_window_is_one_chunk() -> None:
    assert fixed_chunks("12345", chunk_size=5, overlap=2) == ["12345"]


def test_fixed_strategy_has_no_gaps() -> None:
    text = "0123456789"

    chunks = fixed_chunks(text, chunk_size=5, overlap=2)

    assert chunks == ["01234", "34567", "6789"]


@pytest.mark.parametrize(
    ("chunk_size", "overlap", "message"),
    [
        (0, 0, "chunk_size"),
        (-1, 0, "chunk_size"),
        (5, -1, "overlap"),
        (5, 5, "smaller"),
        (5, 6, "smaller"),
        (True, 0, "chunk_size"),
        (5, False, "overlap"),
    ],
)
def test_fixed_strategy_rejects_invalid_configuration(
    chunk_size: int, overlap: int, message: str
) -> None:
    with pytest.raises(ChunkingError, match=message):
        fixed_chunks("text", chunk_size=chunk_size, overlap=overlap)


def test_sentence_strategy_returns_one_sentence_per_chunk() -> None:
    text = "First sentence. Is this the second? Yes, it is!"

    assert sentence_chunks(text) == [
        "First sentence.",
        "Is this the second?",
        "Yes, it is!",
    ]


def test_sentence_strategy_handles_common_abbreviation() -> None:
    text = "Dr. Smith reviewed the document. It passed."

    assert sentence_chunks(text) == [
        "Dr. Smith reviewed the document.",
        "It passed.",
    ]


def test_sentence_strategy_keeps_internal_newline_content() -> None:
    chunks = sentence_chunks("A sentence spans\na line. Next sentence.")

    assert chunks == ["A sentence spans\na line.", "Next sentence."]


def test_paragraph_strategy_returns_one_paragraph_per_chunk() -> None:
    text = "First paragraph.\nStill first.\n\nSecond paragraph.\n\n\nThird."

    assert paragraph_chunks(text) == [
        "First paragraph.\nStill first.",
        "Second paragraph.",
        "Third.",
    ]


def test_paragraph_strategy_normalizes_windows_line_endings() -> None:
    assert paragraph_chunks("First\r\n\r\nSecond") == ["First", "Second"]


@pytest.mark.parametrize(
    ("strategy", "expected"),
    [
        ("fixed", ["abcd", "defg", "gh"]),
        ("sentence", ["One.", "Two."]),
        ("paragraph", ["One. Two."]),
        (ChunkingStrategy.PARAGRAPH, ["One. Two."]),
    ],
)
def test_chunk_text_dispatches_to_selected_strategy(strategy, expected) -> None:
    assert chunk_text("One. Two." if strategy != "fixed" else "abcdefgh", strategy, chunk_size=4, overlap=1) == expected


def test_chunk_text_rejects_unknown_strategy() -> None:
    with pytest.raises(ChunkingError, match="Unknown chunking strategy"):
        chunk_text("text", "tokens")


@pytest.mark.parametrize("chunker", [fixed_chunks, sentence_chunks, paragraph_chunks])
def test_chunkers_reject_non_string_text(chunker) -> None:
    with pytest.raises(TypeError, match="text must be a string"):
        chunker(None)  # type: ignore[arg-type]
