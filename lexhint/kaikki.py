from __future__ import annotations

import io
import unicodedata
import urllib.error
import urllib.request
from collections.abc import Iterator
from urllib.parse import quote

from .download import user_agent
from .store import iter_jsonl_entries

KAIKKI_WORD_BASE_URL = "https://kaikki.org/dictionary/All%20languages%20combined/meaning"
USER_AGENT = user_agent()


class DictionaryFetchError(RuntimeError):
    """Raised when a Kaikki word page cannot be fetched or parsed."""


class DictionaryWordNotFound(DictionaryFetchError):
    """Raised when Kaikki has no raw page for the requested exact word."""


def kaikki_word_url(word: str) -> str:
    page = unicodedata.normalize("NFC", word)
    if not page:
        raise ValueError("dictionary word must not be empty")
    first = page[:1]
    first_two = page[:2]
    return (
        f"{KAIKKI_WORD_BASE_URL}/{quote(first, safe='')}/"
        f"{quote(first_two, safe='')}/{quote(page, safe='')}.jsonl"
    )


def iter_word_entries(word: str, *, timeout: float = 30.0) -> Iterator[dict[str, object]]:
    page = unicodedata.normalize("NFC", word)
    url = kaikki_word_url(page)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        response = urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise DictionaryWordNotFound(f"no Kaikki dictionary data for {page!r}") from exc
        raise DictionaryFetchError(f"failed to fetch dictionary data for {page!r}: {exc}") from exc
    except OSError as exc:
        raise DictionaryFetchError(f"failed to fetch dictionary data for {page!r}: {exc}") from exc

    with response as binary:
        try:
            text = io.TextIOWrapper(binary, encoding="utf-8")
            yield from iter_jsonl_entries(text)
        except (UnicodeError, ValueError) as exc:
            raise DictionaryFetchError(
                f"invalid Kaikki JSONL for dictionary word {page!r}: {exc}"
            ) from exc


def fetch_word_entries(word: str, *, timeout: float = 30.0) -> tuple[dict[str, object], ...]:
    return tuple(iter_word_entries(word, timeout=timeout))


__all__ = [
    "DictionaryFetchError",
    "DictionaryWordNotFound",
    "KAIKKI_WORD_BASE_URL",
    "USER_AGENT",
    "fetch_word_entries",
    "iter_word_entries",
    "kaikki_word_url",
]
