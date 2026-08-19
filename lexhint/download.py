from __future__ import annotations

import gzip
import os
import tempfile
import urllib.request
from pathlib import Path

SUPPORTED_LANGUAGES = frozenset({"cs", "de", "en", "es", "fr", "it", "pt"})
_FREQUENCY_BASE_URL = (
    "https://raw.githubusercontent.com/hermitdave/FrequencyWords/"
    "master/content/2018/{language}/{language}_50k.txt"
)
KAIKKI_RAW_URL = "https://kaikki.org/dictionary/raw-wiktextract-data.jsonl.gz"


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


def cached_wordlist_path(language: str) -> Path:
    language = language.lower().split("-", 1)[0]
    return cache_dir() / "words" / f"{language}.txt.gz"


def cached_dictionary_path(language: str) -> Path:
    language = language.lower().split("-", 1)[0]
    return cache_dir() / "dictionaries" / f"{language}.sqlite3"


def wordlist_source_url(language: str) -> str:
    language = language.lower().split("-", 1)[0]
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"unsupported language: {language!r}")
    return _FREQUENCY_BASE_URL.format(language=language)


def _normalize_frequency_source(data: bytes) -> list[str]:
    text = data.decode("utf-8")
    words: list[str] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            word, count = line.rsplit(maxsplit=1)
            int(count)
        except (ValueError, TypeError) as exc:
            raise DownloadError(f"invalid FrequencyWords line: {raw_line!r}") from exc
        normalized = word.casefold()
        if normalized and normalized not in seen:
            seen.add(normalized)
            words.append(normalized)
    if len(words) < 45_000:
        raise DownloadError(
            f"downloaded word list is unexpectedly small ({len(words)} unique words)"
        )
    return words[:50_000]


def fetch_wordlist(language: str, *, force: bool = False, timeout: float = 30.0) -> Path:
    """Download and normalize one upstream 50k frequency list into the user cache."""
    target = cached_wordlist_path(language)
    if target.exists() and not force:
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    url = wordlist_source_url(language)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "lexhint/0 (+https://github.com/buchwandler/lexhint)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read()
    except OSError as exc:
        raise DownloadError(f"failed to download {url}: {exc}") from exc

    words = _normalize_frequency_source(data)
    fd, tmp_name = tempfile.mkstemp(prefix="lexhint-", suffix=".txt.gz", dir=target.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        with gzip.open(tmp, "wt", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(words))
            handle.write("\n")
        tmp.replace(target)
    finally:
        tmp.unlink(missing_ok=True)
    return target
