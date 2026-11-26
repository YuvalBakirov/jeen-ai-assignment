from __future__ import annotations

from pathlib import Path

import pytest

from src.config import ConfigurationError, load_settings


@pytest.fixture(autouse=True)
def clean_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("POSTGRES_URL", raising=False)


def write_env(tmp_path: Path, contents: str) -> Path:
    env_file = tmp_path / ".env"
    env_file.write_text(contents, encoding="utf-8")
    return env_file


def test_loads_valid_settings_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "secret-key")
    monkeypatch.setenv("POSTGRES_URL", "postgresql://jeen:secret@localhost:5432/jeen")

    settings = load_settings(env_file="missing.env")

    assert settings.gemini_api_key == "secret-key"
    assert settings.postgres_url.endswith("/jeen")


def test_loads_settings_from_env_file(tmp_path: Path) -> None:
    env_file = write_env(
        tmp_path,
        "GEMINI_API_KEY=file-secret\n"
        "POSTGRES_URL=postgresql://jeen:secret@localhost:5432/jeen\n",
    )

    settings = load_settings(env_file)

    assert settings.gemini_api_key == "file-secret"


def test_process_environment_overrides_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = write_env(
        tmp_path,
        "GEMINI_API_KEY=file-secret\n"
        "POSTGRES_URL=postgresql://jeen:file@localhost:5432/jeen\n",
    )
    monkeypatch.setenv("GEMINI_API_KEY", "process-secret")
    monkeypatch.setenv("POSTGRES_URL", "postgresql://jeen:process@localhost:5432/jeen")

    settings = load_settings(env_file)

    assert settings.gemini_api_key == "process-secret"
    assert "process" in settings.postgres_url


def test_missing_api_key_has_safe_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_URL", "postgresql://jeen:secret@localhost:5432/jeen")

    with pytest.raises(ConfigurationError, match="Set GEMINI_API_KEY"):
        load_settings(env_file="missing.env")


def test_missing_postgres_url_has_safe_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "secret-key")

    with pytest.raises(ConfigurationError, match="Set POSTGRES_URL"):
        load_settings(env_file="missing.env")


def test_rejects_placeholder_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "YOUR_API_KEY")
    monkeypatch.setenv("POSTGRES_URL", "postgresql://jeen:secret@localhost:5432/jeen")

    with pytest.raises(ConfigurationError, match="placeholder GEMINI_API_KEY"):
        load_settings(env_file="missing.env")


def test_rejects_placeholder_database_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "secret-key")
    monkeypatch.setenv("POSTGRES_URL", "postgresql://jeen:REPLACE_ME@localhost:5432/jeen")

    with pytest.raises(ConfigurationError, match="placeholder password"):
        load_settings(env_file="missing.env")


def test_rejects_non_postgres_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "secret-key")
    monkeypatch.setenv("POSTGRES_URL", "mysql://jeen:secret@localhost:3306/jeen")

    with pytest.raises(ConfigurationError, match="must start with"):
        load_settings(env_file="missing.env")


def test_rejects_url_without_host(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "secret-key")
    monkeypatch.setenv("POSTGRES_URL", "postgresql:///jeen")

    with pytest.raises(ConfigurationError, match="database host"):
        load_settings(env_file="missing.env")


def test_rejects_url_without_database_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "secret-key")
    monkeypatch.setenv("POSTGRES_URL", "postgresql://jeen:secret@localhost:5432")

    with pytest.raises(ConfigurationError, match="database name"):
        load_settings(env_file="missing.env")


def test_settings_repr_hides_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "never-print-this-key")
    monkeypatch.setenv("POSTGRES_URL", "postgresql://jeen:secret@localhost:5432/jeen")

    representation = repr(load_settings(env_file="missing.env"))

    assert "never-print-this-key" not in representation
    assert "gemini_api_key='***'" in representation


def test_settings_repr_hides_database_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "secret-key")
    monkeypatch.setenv(
        "POSTGRES_URL", "postgresql://jeen:never-print-this-password@localhost:5432/jeen"
    )

    representation = repr(load_settings(env_file="missing.env"))

    assert "never-print-this-password" not in representation
    assert "jeen:***@localhost" in representation
