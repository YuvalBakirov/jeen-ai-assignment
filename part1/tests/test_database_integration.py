"""Opt-in integration tests against a disposable PostgreSQL schema."""
from __future__ import annotations

import hashlib
import os
import uuid

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from src.database import Database


@pytest.fixture
def database():
    url = os.getenv('TEST_POSTGRES_URL')
    if not url:
        pytest.skip('Set TEST_POSTGRES_URL to a disposable PostgreSQL database')
    schema = 'jeen_test_' + uuid.uuid4().hex
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute('CREATE EXTENSION IF NOT EXISTS vector')
        conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    scoped = make_conninfo(url, options=f'-c search_path={schema},public')
    db = Database(scoped)
    try:
        db.initialize()
        yield db, scoped
    finally:
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def test_insert_duplicate_strategy_and_cosine_search(database):
    db, _ = database
    digest = hashlib.sha256(b'document').hexdigest()
    v1 = [1.0] + [0.0] * 767
    v2 = [0.0, 1.0] + [0.0] * 766
    assert db.store_document(digest, 'paragraph', 'sample.docx', ['library', 'planet'], [v1, v2])
    with psycopg.connect(database[1]) as conn:
        rows = conn.execute('SELECT id, chunk_text, embedding, filename, split_strategy, created_at FROM chunks ORDER BY chunk_index').fetchall()
        assert len(rows) == 2
        assert rows[0][1] == 'library'
        assert rows[0][3:5] == ('sample.docx', 'paragraph')
        assert rows[0][5] is not None
    assert not db.store_document(digest, 'paragraph', 'other.docx', ['library'], [v1])
    assert db.store_document(digest, 'sentence', 'sample.docx', ['library'], [v1])
    results = db.search(v1, limit=2, strategy='paragraph')
    assert [result.content for result in results] == ['library', 'planet']
    assert results[0].similarity == pytest.approx(1.0)
    assert db.search(v1, strategy='fixed') == []


def test_insert_failure_rolls_back_all_rows(database):
    db, scoped = database
    digest = hashlib.sha256(b'rollback').hexdigest()
    vector = [1.0] + [0.0] * 767
    # A NUL is rejected by PostgreSQL during the second row insertion.
    with pytest.raises((psycopg.Error, ValueError)):
        db.store_document(digest, 'fixed', 'sample.pdf', ['valid', 'bad\x00text'], [vector, vector])
    with psycopg.connect(scoped) as conn:
        assert conn.execute('SELECT count(*) FROM documents').fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM chunks').fetchone()[0] == 0


def test_invalid_vectors_are_rejected(database):
    db, _ = database
    digest = hashlib.sha256(b'invalid').hexdigest()
    with pytest.raises(ValueError):
        db.store_document(digest, 'fixed', 'sample.pdf', ['test'], [[0.0] * 768])
    with pytest.raises(ValueError):
        db.search([float('nan')] * 768)


def test_legacy_rows_are_migrated_without_loss(database):
    db, scoped = database
    digest = hashlib.sha256(b'legacy').hexdigest()
    vector = [1.0] + [0.0] * 767
    assert db.store_document(digest, 'fixed', 'legacy.pdf', ['preserved'], [vector])
    with psycopg.connect(scoped) as conn:
        conn.execute('ALTER TABLE chunks DROP COLUMN chunk_text, DROP COLUMN filename, DROP COLUMN split_strategy, DROP COLUMN created_at')
    db.initialize()
    db.initialize()
    with psycopg.connect(scoped) as conn:
        row = conn.execute('SELECT chunk_text, filename, split_strategy, created_at FROM chunks').fetchone()
    assert row[:3] == ('preserved', 'legacy.pdf', 'fixed')
    assert row[3] is not None
    assert db.search(vector)[0].content == 'preserved'
