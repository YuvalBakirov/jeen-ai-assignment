"""Transactional storage of document chunks and pgvector embeddings."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import math

import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector


@dataclass(frozen=True)
class SearchResult:
    filename: str
    strategy: str
    chunk_index: int
    content: str
    similarity: float


class Database:
    """Connect to a PostgreSQL database using a caller-supplied URL."""

    def __init__(self, url: str) -> None:
        self._url = url

    def initialize(self) -> None:
        with psycopg.connect(self._url) as conn:
            conn.execute('CREATE EXTENSION IF NOT EXISTS vector')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS documents (
                    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    content_hash CHAR(64) NOT NULL,
                    strategy TEXT NOT NULL CHECK (strategy IN ('fixed', 'sentence', 'paragraph')),
                    filename TEXT NOT NULL,
                    UNIQUE (content_hash, strategy)
                )
            ''')

            conn.execute('''
                CREATE TABLE IF NOT EXISTS chunks (
                    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
                    content TEXT NOT NULL,
                    chunk_text TEXT GENERATED ALWAYS AS (content) STORED,
                    embedding vector(768) NOT NULL,
                    filename TEXT NOT NULL,
                    split_strategy TEXT NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (document_id, chunk_index)
                )
            ''')
            # Upgrade earlier project databases in place; existing timestamps
            # reflect migration time because the original schema stored none.
            conn.execute('ALTER TABLE chunks ADD COLUMN IF NOT EXISTS chunk_text TEXT GENERATED ALWAYS AS (content) STORED')
            conn.execute('ALTER TABLE chunks ADD COLUMN IF NOT EXISTS filename TEXT')
            conn.execute('ALTER TABLE chunks ADD COLUMN IF NOT EXISTS split_strategy TEXT')
            conn.execute('ALTER TABLE chunks ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP')
            conn.execute('''UPDATE chunks c SET filename = d.filename, split_strategy = d.strategy
                            FROM documents d WHERE c.document_id = d.id
                            AND (c.filename IS NULL OR c.split_strategy IS NULL)''')
            conn.execute('ALTER TABLE chunks ALTER COLUMN filename SET NOT NULL')
            conn.execute('ALTER TABLE chunks ALTER COLUMN split_strategy SET NOT NULL')

    def contains_document(self, content_hash: str, strategy: str) -> bool:
        with psycopg.connect(self._url) as conn:
            return conn.execute(
                'SELECT 1 FROM documents WHERE content_hash = %s AND strategy = %s',
                (content_hash, strategy),
            ).fetchone() is not None

    def store_document(self, content_hash: str, strategy: str, filename: str,
                       chunks: Sequence[str], embeddings: Sequence[Sequence[float]]) -> bool:
        """Insert all chunks atomically, returning False for an existing document."""
        if not chunks or len(chunks) != len(embeddings):
            raise ValueError('Chunks and embeddings must be non-empty and have equal lengths.')
        if len(content_hash) != 64 or any(c not in '0123456789abcdef' for c in content_hash):
            raise ValueError('content_hash must be a lowercase SHA-256 digest.')
        if any(not chunk.strip() for chunk in chunks):
            raise ValueError('Chunks must not be empty.')
        if any(len(vector) != 768 or not all(math.isfinite(x) for x in vector)
               or not any(vector) for vector in embeddings):
            raise ValueError('Every embedding must be a finite nonzero 768-dimensional vector.')
        with psycopg.connect(self._url) as conn:
            register_vector(conn)
            row = conn.execute('''
                INSERT INTO documents (content_hash, strategy, filename)
                VALUES (%s, %s, %s)
                ON CONFLICT (content_hash, strategy) DO NOTHING RETURNING id
            ''', (content_hash, strategy, filename)).fetchone()
            if row is None:
                return False
            with conn.cursor() as cur:
                cur.executemany('''
                    INSERT INTO chunks (document_id, chunk_index, content, embedding, filename, split_strategy)
                    VALUES (%s, %s, %s, %s, %s, %s)
                ''', [(row[0], i, chunk, Vector(vector), filename, strategy)
                      for i, (chunk, vector) in enumerate(zip(chunks, embeddings))])
        return True

    def search(self, query_embedding: Sequence[float], limit: int = 5,
               strategy: str | None = None) -> list[SearchResult]:
        if (len(query_embedding) != 768 or not all(math.isfinite(x) for x in query_embedding)
                or not any(query_embedding) or limit < 1):
            raise ValueError('Expected a finite nonzero 768-dimensional query and a positive limit.')
        with psycopg.connect(self._url) as conn:
            register_vector(conn)
            rows = conn.execute('''
                SELECT d.filename, d.strategy, c.chunk_index, c.content,
                       1 - (c.embedding <=> %s) AS similarity
                FROM chunks c JOIN documents d ON d.id = c.document_id
                WHERE (%s::text IS NULL OR d.strategy = %s)
                ORDER BY c.embedding <=> %s, c.id LIMIT %s
            ''', (Vector(query_embedding), strategy, strategy, Vector(query_embedding), limit)).fetchall()
        return [SearchResult(*row) for row in rows]
