from __future__ import annotations

import os
import sys
import urllib.request
from collections.abc import Mapping
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import BinaryIO, cast

from .languages import SUPPORTED_LANGUAGES, normalize_language

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


def data_dir() -> Path:
    """Return the persistent per-user dataset directory."""
    explicit = os.environ.get("LEXHINT_DATA_DIR")
    if explicit:
        return Path(explicit).expanduser()
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA")
        return (Path(root).expanduser() if root else Path.home() / "AppData" / "Local") / "lexhint"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "lexhint"
    xdg = os.environ.get("XDG_DATA_HOME")
    return (Path(xdg).expanduser() if xdg else Path.home() / ".local" / "share") / "lexhint"


def request(
    url: str,
    *,
    accept: str | None = None,
    token: str | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: float = 30.0,
) -> BinaryIO:
    """Open a URL with Lexhint headers and bounded network time."""
    request_headers = {"User-Agent": user_agent()}
    if accept:
        request_headers["Accept"] = accept
    if token:
        request_headers["Authorization"] = f"Bearer {token}"
    if headers:
        request_headers.update(headers)
    return cast(
        BinaryIO,
        urllib.request.urlopen(
            urllib.request.Request(url, headers=request_headers), timeout=timeout
        ),
    )


def cached_dictionary_path(language: str) -> Path:
    candidate = language.strip().lower().replace("_", "-")
    language = "en" if candidate in {"en-us", "en-gb"} else normalize_language(language)
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
    "data_dir",
    "package_version",
    "request",
    "user_agent",
]
