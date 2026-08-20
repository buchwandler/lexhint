from __future__ import annotations

import os
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

SUPPORTED_LANGUAGES = frozenset({"cs", "de", "en", "es", "fr", "it", "pt"})
KAIKKI_RAW_URL = "https://kaikki.org/dictionary/raw-wiktextract-data.jsonl.gz"
_PROJECT_URL = "https://github.com/buchwandler/lexhint"


class DownloadError(RuntimeError):
    """Raised when an external lexical resource cannot be downloaded or validated."""


def cache_dir() -> Path:
    """Return the per-user lexhint cache directory without external dependencies."""
    explicit = os.environ.get("LEXHINT_CACHE_DIR")
    if explicit:
        return Path(explicit).expanduser()
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        return Path(xdg).expanduser() / "lexhint"
    return Path.home() / ".cache" / "lexhint"


def cached_dictionary_path(language: str) -> Path:
    language = language.lower().split("-", 1)[0]
    return cache_dir() / "dictionaries" / f"{language}.sqlite3"


def package_version() -> str:
    """Return the installed package version for external request identity."""
    try:
        return version("lexhint")
    except PackageNotFoundError:
        return "0+unknown"


def user_agent() -> str:
    return f"lexhint/{package_version()} (+{_PROJECT_URL})"


__all__ = [
    "KAIKKI_RAW_URL",
    "SUPPORTED_LANGUAGES",
    "DownloadError",
    "cache_dir",
    "cached_dictionary_path",
    "package_version",
    "user_agent",
]
