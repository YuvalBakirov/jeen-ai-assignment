"""Centralized, secret-safe application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"
POSTGRES_SCHEMES = {"postgres", "postgresql"}
PLACEHOLDER_VALUES = {
    "change_me",
    "changeme",
    "example",
    "placeholder",
    "replace_me",
    "your_api_key",
    "your_password",
}


class ConfigurationError(ValueError):
    """Raised when required configuration is absent or unsafe."""


@dataclass(frozen=True, repr=False, slots=True)
class Settings:
    """Validated runtime settings.

    The custom representation deliberately masks credentials so accidental
    logging cannot disclose the API key or database password.
    """

    gemini_api_key: str
    postgres_url: str

    def __repr__(self) -> str:
        return (
            "Settings(gemini_api_key='***', "
            f"postgres_url='{_redact_postgres_url(self.postgres_url)}')"
        )


def _is_placeholder(value: str) -> bool:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    return normalized in PLACEHOLDER_VALUES or normalized.startswith("your_")


def _redact_postgres_url(url: str) -> str:
    parsed = urlsplit(url)
    if not parsed.hostname:
        return "***"

    host = parsed.hostname
    if ":" in host:
        host = f"[{host}]"
    port = f":{parsed.port}" if parsed.port else ""
    username = f"{parsed.username}:***@" if parsed.username else ""
    safe_netloc = f"{username}{host}{port}"
    return urlunsplit((parsed.scheme, safe_netloc, parsed.path, "", ""))


def _validate_postgres_url(url: str) -> None:
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise ConfigurationError("POSTGRES_URL is not a valid PostgreSQL URL.") from exc

    if parsed.scheme not in POSTGRES_SCHEMES:
        raise ConfigurationError(
            "POSTGRES_URL must start with postgres:// or postgresql://."
        )
    if not parsed.hostname:
        raise ConfigurationError("POSTGRES_URL must include a database host.")
    if port is not None and not 1 <= port <= 65535:
        raise ConfigurationError("POSTGRES_URL contains an invalid port.")
    if not parsed.path or parsed.path == "/":
        raise ConfigurationError("POSTGRES_URL must include a database name.")
    if parsed.password and _is_placeholder(parsed.password):
        raise ConfigurationError(
            "Replace the placeholder password in POSTGRES_URL before running the app."
        )


def load_settings(env_file: str | Path | None = None) -> Settings:
    """Load and validate settings from an env file and the process environment.

    Existing process variables take precedence over values in the env file.
    Error messages identify the setting but never include its value.
    """

    dotenv_path = Path(env_file) if env_file is not None else DEFAULT_ENV_FILE
    load_dotenv(dotenv_path=dotenv_path, override=False)

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    postgres_url = os.getenv("POSTGRES_URL", "").strip()

    if not api_key:
        raise ConfigurationError(
            "Set GEMINI_API_KEY in .env or the environment."
        )
    if _is_placeholder(api_key):
        raise ConfigurationError("Replace the placeholder GEMINI_API_KEY before running the app.")
    if not postgres_url:
        raise ConfigurationError("Set POSTGRES_URL in .env or the environment.")

    _validate_postgres_url(postgres_url)
    return Settings(gemini_api_key=api_key, postgres_url=postgres_url)
