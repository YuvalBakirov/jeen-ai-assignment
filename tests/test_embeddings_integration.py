"""Opt-in live Gemini integration verification."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from src.embeddings import EMBEDDING_DIMENSIONS, GeminiEmbeddingClient

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

@pytest.mark.skipif(
    os.getenv("RUN_LIVE_GEMINI") != "1" or not os.getenv("GEMINI_API_KEY"),
    reason="Set RUN_LIVE_GEMINI=1 and GEMINI_API_KEY for live verification.",
)
def test_live_gemini_count_and_embedding() -> None:
    client = GeminiEmbeddingClient(os.environ["GEMINI_API_KEY"])

    assert client.count_tokens("A short document retrieval test.") > 0
    [vector] = client.embed_documents(["A short document retrieval test."])
    assert len(vector) == EMBEDDING_DIMENSIONS
    assert sum(value * value for value in vector) == pytest.approx(1.0, abs=1e-6)
