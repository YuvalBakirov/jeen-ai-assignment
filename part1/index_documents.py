"""Command-line entry point for document indexing."""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections.abc import Sequence
from pathlib import Path

import psycopg
from src.chunking import chunk_text, ChunkingError
from src.config import load_settings, ConfigurationError
from src.database import Database
from src.document_loader import load_document, DocumentLoadError
from src.embeddings import GeminiEmbeddingClient, EmbeddingError


STRATEGIES = ("fixed", "sentence", "paragraph")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Index a PDF or DOCX document.")
    parser.add_argument("--file", required=True, help="Path to a PDF or DOCX file.")
    parser.add_argument(
        "--strategy",
        required=True,
        choices=STRATEGIES,
        help="Chunking strategy to use.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        path = Path(args.file).expanduser()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        text = load_document(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Document changed during extraction; retry indexing.")
        chunks = chunk_text(text, args.strategy)
        settings = load_settings()
        db = Database(settings.postgres_url)
        db.initialize()
        if db.contains_document(digest, args.strategy):
            print(f"Already indexed: {path.name} ({args.strategy}).")
            return 0
        vectors = GeminiEmbeddingClient(settings.gemini_api_key).embed_documents(chunks)
        inserted = db.store_document(digest, args.strategy, path.name, chunks, vectors)
        print(f"{'Indexed' if inserted else 'Already indexed'}: {path.name} ({args.strategy}, {len(chunks)} chunks).")
        return 0
    except (DocumentLoadError, ChunkingError, ConfigurationError, EmbeddingError, psycopg.Error, OSError, ValueError) as exc:
        print(f"Indexing failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
