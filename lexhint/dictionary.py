from __future__ import annotations

from pathlib import Path

from .kaikki import DictionaryFetchError, DictionaryWordNotFound
from .lexicon import (
    Lexicon,
    LexiconCapabilityError,
    LexiconCoverageError,
    LexiconIncompatible,
    LexiconNotInstalled,
)
from .models import DictionaryFetchResult

# Temporary source-compatible name for internal callers during the pre-release migration.
Dictionary = Lexicon
DictionaryCoverageError = LexiconCoverageError
DictionaryIncompatible = LexiconIncompatible
DictionaryNotInstalled = LexiconNotInstalled
DictionaryOfflineError = LexiconCapabilityError


def fetch_dictionary_word(
    language: str,
    word: str,
    *,
    path: str | Path | None = None,
    refresh: bool = False,
    offline: bool = False,
    timeout: float = 30.0,
) -> DictionaryFetchResult:
    del language, word, path, refresh, offline, timeout
    raise DictionaryFetchError(
        "runtime word fetching was removed; build a complete local Lexhint artifact instead"
    )


__all__ = [
    "Dictionary",
    "DictionaryCoverageError",
    "DictionaryFetchError",
    "DictionaryIncompatible",
    "DictionaryNotInstalled",
    "DictionaryOfflineError",
    "DictionaryWordNotFound",
    "Lexicon",
    "LexiconCapabilityError",
    "LexiconCoverageError",
    "LexiconIncompatible",
    "LexiconNotInstalled",
    "fetch_dictionary_word",
]
