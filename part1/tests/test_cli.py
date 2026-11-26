from __future__ import annotations

import pytest

import index_documents
import search


def test_index_help_lists_required_options(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        index_documents.main(["--help"])

    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "--file FILE" in output
    assert "--strategy {fixed,sentence,paragraph}" in output


def test_search_help_lists_supported_options(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        search.main(["--help"])

    assert exc_info.value.code == 0
    output = capsys.readouterr().out
    assert "--query QUERY" in output
    assert "--limit LIMIT" in output


def test_index_requires_file() -> None:
    with pytest.raises(SystemExit) as exc_info:
        index_documents.main(["--strategy", "fixed"])

    assert exc_info.value.code == 2


def test_index_rejects_unknown_strategy() -> None:
    with pytest.raises(SystemExit) as exc_info:
        index_documents.main(["--file", "sample.pdf", "--strategy", "unknown"])

    assert exc_info.value.code == 2


def test_search_requires_query() -> None:
    with pytest.raises(SystemExit) as exc_info:
        search.main([])

    assert exc_info.value.code == 2


def test_search_uses_default_limit() -> None:
    args = search.build_parser().parse_args(["--query", "hello"])

    assert args.limit == 5
    assert args.strategy is None


def test_search_rejects_non_positive_limit() -> None:
    with pytest.raises(SystemExit) as exc_info:
        search.main(["--query", "hello", "--limit", "0"])

    assert exc_info.value.code == 2
