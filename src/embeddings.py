"""Gemini embedding integration with validation, batching, and retries."""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Sequence
from typing import Any, TypeVar

from google import genai
from google.genai import errors, types


EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIMENSIONS = 768
EMBEDDING_BATCH_SIZE = 16
MAX_CHUNK_TOKENS = 1_800
DOCUMENT_TASK_TYPE = "RETRIEVAL_DOCUMENT"
QUERY_TASK_TYPE = "RETRIEVAL_QUERY"
_RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}

T = TypeVar("T")


class EmbeddingError(RuntimeError):
    """Raised when an embedding operation cannot be completed safely."""


class TokenLimitError(EmbeddingError):
    """Raised when text exceeds the approved working token limit."""


def l2_normalize(values: Sequence[float]) -> list[float]:
    """Return a finite unit-length vector without adding a NumPy dependency."""

    if not values:
        raise EmbeddingError("Gemini returned an empty embedding vector.")
    vector = [float(value) for value in values]
    if not all(math.isfinite(value) for value in vector):
        raise EmbeddingError("Gemini returned a non-finite embedding value.")
    magnitude = math.hypot(*vector)
    if magnitude == 0:
        raise EmbeddingError("Gemini returned a zero-length embedding vector.")
    return [value / magnitude for value in vector]


def _validate_text(text: str, label: str = "text") -> str:
    if not isinstance(text, str):
        raise TypeError(f"{label} must be a string")
    prepared = text.strip()
    if not prepared:
        raise EmbeddingError(f"{label} must not be empty")
    return prepared


class GeminiEmbeddingClient:
    """Small synchronous adapter around the Google Gen AI embedding API."""

    def __init__(
        self,
        api_key: str,
        *,
        client: Any | None = None,
        max_attempts: int = 3,
        retry_delay_seconds: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise EmbeddingError("A non-empty Gemini API key is required.")
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts < 1:
            raise ValueError("max_attempts must be a positive integer")
        if retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds must be non-negative")

        self._client = client if client is not None else genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=30_000),
        )
        self._max_attempts = max_attempts
        self._retry_delay_seconds = retry_delay_seconds
        self._sleep = sleep

    def __repr__(self) -> str:
        return (
            "GeminiEmbeddingClient(model='gemini-embedding-001', "
            "dimensions=768, api_key='***')"
        )

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        if isinstance(exc, errors.ServerError):
            return True
        if isinstance(exc, errors.APIError):
            return exc.code in _RETRYABLE_STATUS_CODES
        return isinstance(exc, (ConnectionError, OSError, TimeoutError))

    def _call_with_retry(self, operation: Callable[[], T], operation_name: str) -> T:
        for attempt in range(1, self._max_attempts + 1):
            try:
                return operation()
            except Exception as exc:
                if attempt == self._max_attempts or not self._is_retryable(exc):
                    raise EmbeddingError(
                        f"Gemini {operation_name} failed after {attempt} attempt(s)."
                    ) from exc
                delay = self._retry_delay_seconds * (2 ** (attempt - 1))
                self._sleep(delay)
        raise AssertionError("retry loop ended unexpectedly")

    def count_tokens(self, text: str) -> int:
        """Count tokens for one exact embedding input."""

        prepared = _validate_text(text)
        response = self._call_with_retry(
            lambda: self._client.models.count_tokens(
                model=EMBEDDING_MODEL,
                contents=prepared,
            ),
            "token counting",
        )
        count = getattr(response, "total_tokens", None)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise EmbeddingError("Gemini returned an invalid token count.")
        return count

    def _validate_token_limit(self, text: str, label: str) -> str:
        prepared = _validate_text(text, label)
        token_count = self.count_tokens(prepared)
        if token_count > MAX_CHUNK_TOKENS:
            raise TokenLimitError(
                f"{label} contains {token_count} tokens; the working limit is "
                f"{MAX_CHUNK_TOKENS}."
            )
        return prepared

    def _embed_batch(self, texts: list[str], task_type: str) -> list[list[float]]:
        response = self._call_with_retry(
            lambda: self._client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=texts,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=EMBEDDING_DIMENSIONS,
                ),
            ),
            "embedding",
        )
        embeddings = getattr(response, "embeddings", None)
        if embeddings is None or len(embeddings) != len(texts):
            raise EmbeddingError(
                "Gemini returned a different number of embeddings than inputs."
            )

        normalized: list[list[float]] = []
        for embedding in embeddings:
            values = getattr(embedding, "values", None)
            if values is None or len(values) != EMBEDDING_DIMENSIONS:
                actual = 0 if values is None else len(values)
                raise EmbeddingError(
                    f"Gemini returned {actual} dimensions; expected "
                    f"{EMBEDDING_DIMENSIONS}."
                )
            normalized.append(l2_normalize(values))
        return normalized

    def embed_documents(self, chunks: Sequence[str]) -> list[list[float]]:
        """Validate and embed document chunks in synchronous batches of 16."""

        if isinstance(chunks, (str, bytes)):
            raise TypeError("chunks must be a sequence of strings, not one string")
        if not chunks:
            return []

        prepared = [
            self._validate_token_limit(chunk, f"chunk {index}")
            for index, chunk in enumerate(chunks, start=1)
        ]
        output: list[list[float]] = []
        for start in range(0, len(prepared), EMBEDDING_BATCH_SIZE):
            batch = prepared[start : start + EMBEDDING_BATCH_SIZE]
            output.extend(self._embed_batch(batch, DOCUMENT_TASK_TYPE))
        return output

    def embed_query(self, query: str) -> list[float]:
        """Embed a search query using the retrieval-query task type."""

        prepared = self._validate_token_limit(query, "query")
        return self._embed_batch([prepared], QUERY_TASK_TYPE)[0]
