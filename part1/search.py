"""Command-line entry point for semantic search."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

import psycopg
from index_documents import STRATEGIES
from src.config import load_settings, ConfigurationError
from src.database import Database
from src.embeddings import GeminiEmbeddingClient, EmbeddingError


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Search indexed document chunks.")
    parser.add_argument("--query", required=True, help="Natural-language search query.")
    parser.add_argument(
        "--limit",
        type=positive_int,
        default=5,
        help="Maximum number of results (default: 5).",
    )
    parser.add_argument(
        "--strategy",
        choices=STRATEGIES,
        help="Optionally restrict results to one chunking strategy.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings()
        db = Database(settings.postgres_url)
        db.initialize()
        vector = GeminiEmbeddingClient(settings.gemini_api_key).embed_query(args.query)
        results = db.search(vector, args.limit, args.strategy)
        if not results:
            print("No matching chunks found.")
        for result in results:
            print(f"{result.filename} | {result.strategy} | chunk {result.chunk_index} | similarity {result.similarity:.4f}")
            print(result.content, end="\n\n")
        return 0
    except (ConfigurationError, EmbeddingError, psycopg.Error, ValueError) as exc:
        print(f"Search failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
