from __future__ import annotations

import math
from types import SimpleNamespace

import pytest
from google.genai import errors

from src.embeddings import (
    DOCUMENT_TASK_TYPE,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
    MAX_CHUNK_TOKENS,
    QUERY_TASK_TYPE,
    EmbeddingError,
    GeminiEmbeddingClient,
    TokenLimitError,
    l2_normalize,
)


class FakeModels:
    def __init__(self, *, token_count: int = 10) -> None:
        self.token_count = token_count
        self.count_calls: list[dict] = []
        self.embed_calls: list[dict] = []

    def count_tokens(self, **kwargs):
        self.count_calls.append(kwargs)
        return SimpleNamespace(total_tokens=self.token_count)

    def embed_content(self, **kwargs):
        self.embed_calls.append(kwargs)
        contents = kwargs["contents"]
        return SimpleNamespace(
            embeddings=[
                SimpleNamespace(values=[float(index + 1)] * EMBEDDING_DIMENSIONS)
                for index, _ in enumerate(contents)
            ]
        )


def make_client(models: FakeModels, **kwargs) -> GeminiEmbeddingClient:
    return GeminiEmbeddingClient(
        "test-key",
        client=SimpleNamespace(models=models),
        retry_delay_seconds=0,
        **kwargs,
    )


def test_l2_normalize_returns_unit_vector() -> None:
    normalized = l2_normalize([3.0, 4.0])

    assert normalized == pytest.approx([0.6, 0.8])
    assert math.sqrt(sum(value * value for value in normalized)) == pytest.approx(1.0)


def test_normalization_avoids_overflow_for_large_finite_values() -> None:
    assert l2_normalize([1e200, 1e200]) == pytest.approx([2 ** -0.5] * 2)


@pytest.mark.parametrize("values", [[], [0.0, 0.0], [math.inf], [math.nan]])
def test_l2_normalize_rejects_invalid_vectors(values) -> None:
    with pytest.raises(EmbeddingError):
        l2_normalize(values)


def test_client_requires_api_key() -> None:
    with pytest.raises(EmbeddingError, match="API key"):
        GeminiEmbeddingClient(" ")


def test_client_repr_does_not_expose_api_key() -> None:
    client = GeminiEmbeddingClient("never-print-this", client=SimpleNamespace())

    assert "never-print-this" not in repr(client)
    assert "api_key='***'" in repr(client)


def test_count_tokens_uses_approved_model() -> None:
    models = FakeModels(token_count=42)
    client = make_client(models)

    assert client.count_tokens("hello") == 42
    assert models.count_calls == [{"model": EMBEDDING_MODEL, "contents": "hello"}]


def test_invalid_token_count_is_rejected() -> None:
    models = FakeModels(token_count=-1)

    with pytest.raises(EmbeddingError, match="invalid token count"):
        make_client(models).count_tokens("hello")


def test_document_embedding_uses_approved_configuration() -> None:
    models = FakeModels()
    vectors = make_client(models).embed_documents(["first", "second"])

    call = models.embed_calls[0]
    assert call["model"] == "gemini-embedding-001"
    assert call["contents"] == ["first", "second"]
    assert call["config"].task_type == DOCUMENT_TASK_TYPE
    assert call["config"].output_dimensionality == 768
    assert len(vectors) == 2
    assert all(len(vector) == EMBEDDING_DIMENSIONS for vector in vectors)
    assert all(math.sqrt(sum(value * value for value in vector)) == pytest.approx(1.0) for vector in vectors)


def test_document_embedding_batches_synchronously_in_sixteens() -> None:
    models = FakeModels()
    chunks = [f"chunk-{index}" for index in range(EMBEDDING_BATCH_SIZE * 2 + 1)]

    vectors = make_client(models).embed_documents(chunks)

    assert len(vectors) == len(chunks)
    assert [len(call["contents"]) for call in models.embed_calls] == [16, 16, 1]
    assert [call["contents"][0] for call in models.embed_calls] == [
        "chunk-0",
        "chunk-16",
        "chunk-32",
    ]


def test_empty_document_list_skips_api_calls() -> None:
    models = FakeModels()

    assert make_client(models).embed_documents([]) == []
    assert models.count_calls == []
    assert models.embed_calls == []


def test_document_token_limit_is_enforced_before_embedding() -> None:
    models = FakeModels(token_count=MAX_CHUNK_TOKENS + 1)

    with pytest.raises(TokenLimitError, match="working limit"):
        make_client(models).embed_documents(["too long"])

    assert models.embed_calls == []


def test_query_uses_retrieval_query_task_type() -> None:
    models = FakeModels()

    vector = make_client(models).embed_query("find this")

    assert len(vector) == EMBEDDING_DIMENSIONS
    assert models.embed_calls[0]["contents"] == ["find this"]
    assert models.embed_calls[0]["config"].task_type == QUERY_TASK_TYPE


@pytest.mark.parametrize("value", ["", "   "])
def test_empty_text_is_rejected(value: str) -> None:
    with pytest.raises(EmbeddingError, match="must not be empty"):
        make_client(FakeModels()).embed_query(value)


def test_one_string_is_not_accepted_as_chunk_sequence() -> None:
    with pytest.raises(TypeError, match="sequence of strings"):
        make_client(FakeModels()).embed_documents("one chunk")


def test_wrong_embedding_count_is_rejected() -> None:
    class MissingModels(FakeModels):
        def embed_content(self, **kwargs):
            return SimpleNamespace(embeddings=[])

    with pytest.raises(EmbeddingError, match="different number"):
        make_client(MissingModels()).embed_documents(["text"])


def test_wrong_embedding_dimensions_are_rejected() -> None:
    class ShortModels(FakeModels):
        def embed_content(self, **kwargs):
            return SimpleNamespace(embeddings=[SimpleNamespace(values=[1.0, 2.0])])

    with pytest.raises(EmbeddingError, match="expected 768"):
        make_client(ShortModels()).embed_documents(["text"])


def test_retryable_api_error_uses_exponential_backoff() -> None:
    delays: list[float] = []

    class RetryModels(FakeModels):
        attempts = 0

        def count_tokens(self, **kwargs):
            self.attempts += 1
            if self.attempts < 3:
                raise errors.ServerError(503, {"error": {"message": "temporary"}})
            return SimpleNamespace(total_tokens=5)

    client = GeminiEmbeddingClient(
        "test-key",
        client=SimpleNamespace(models=RetryModels()),
        retry_delay_seconds=0.5,
        sleep=delays.append,
    )

    assert client.count_tokens("hello") == 5
    assert delays == [0.5, 1.0]


def test_non_retryable_api_error_fails_immediately() -> None:
    class UnauthorizedModels(FakeModels):
        attempts = 0

        def count_tokens(self, **kwargs):
            self.attempts += 1
            raise errors.ClientError(401, {"error": {"message": "invalid key"}})

    models = UnauthorizedModels()
    with pytest.raises(EmbeddingError, match="after 1 attempt"):
        make_client(models).count_tokens("hello")

    assert models.attempts == 1
