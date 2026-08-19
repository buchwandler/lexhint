from __future__ import annotations

import gzip
import hashlib
import json
import os
import tempfile
import urllib.request
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

SUPPORTED_LANGUAGES = frozenset({"cs", "de", "en", "es", "fr", "it", "pt"})
WORDLIST_METADATA_SCHEMA_VERSION = 1
_FREQUENCYWORDS_REVISION = "525f9b560de45753a5ea01069454e72e9aa541c6"
_FREQUENCY_BASE_URL = (
    "https://raw.githubusercontent.com/hermitdave/FrequencyWords/"
    f"{_FREQUENCYWORDS_REVISION}/content/2018/{{language}}/{{language}}_50k.txt"
)
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


def cached_wordlist_path(language: str) -> Path:
    language = language.lower().split("-", 1)[0]
    return cache_dir() / "words" / f"{language}.txt.gz"


def cached_wordlist_metadata_path(language: str) -> Path:
    language = language.lower().split("-", 1)[0]
    return cache_dir() / "words" / f"{language}.metadata.json"


def cached_dictionary_path(language: str) -> Path:
    language = language.lower().split("-", 1)[0]
    return cache_dir() / "dictionaries" / f"{language}.sqlite3"


def wordlist_source_url(language: str) -> str:
    language = language.lower().split("-", 1)[0]
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"unsupported language: {language!r}")
    return _FREQUENCY_BASE_URL.format(language=language)


def package_version() -> str:
    """Return the installed package version for external request identity."""
    try:
        return version("lexhint")
    except PackageNotFoundError:
        return "0+unknown"


def user_agent() -> str:
    return f"lexhint/{package_version()} (+{_PROJECT_URL})"


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


def _canonical_wordlist_bytes(words: list[str]) -> bytes:
    return ("\n".join(words) + "\n").encode("utf-8")


def _wordlist_metadata(language: str, words: list[str], source_url: str) -> dict[str, object]:
    return {
        "schema_version": WORDLIST_METADATA_SCHEMA_VERSION,
        "language": language,
        "source": "FrequencyWords",
        "source_revision": _FREQUENCYWORDS_REVISION,
        "source_url": source_url,
        "normalized_sha256": hashlib.sha256(_canonical_wordlist_bytes(words)).hexdigest(),
        "word_count": len(words),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def _read_cached_words(target: Path) -> list[str]:
    with gzip.open(target, "rt", encoding="utf-8") as handle:
        return [line.strip() for line in handle if line.strip()]


def _valid_cached_wordlist(target: Path, language: str) -> bool:
    metadata_path = cached_wordlist_metadata_path(language)
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        words = _read_cached_words(target)
    except (OSError, ValueError, UnicodeError, EOFError, gzip.BadGzipFile):
        return False
    if not isinstance(metadata, dict):
        return False
    expected = _wordlist_metadata(language, words, wordlist_source_url(language))
    return (
        metadata.get("schema_version") == WORDLIST_METADATA_SCHEMA_VERSION
        and metadata.get("language") == language
        and metadata.get("source") == "FrequencyWords"
        and metadata.get("source_revision") == _FREQUENCYWORDS_REVISION
        and metadata.get("source_url") == expected["source_url"]
        and metadata.get("normalized_sha256") == expected["normalized_sha256"]
        and metadata.get("word_count") == len(words)
    )


def fetch_wordlist(language: str, *, force: bool = False, timeout: float = 30.0) -> Path:
    """Download and normalize one upstream 50k frequency list into the user cache."""
    target = cached_wordlist_path(language)
    language = language.lower().split("-", 1)[0]
    if target.exists() and not force and _valid_cached_wordlist(target, language):
        return target

    target.parent.mkdir(parents=True, exist_ok=True)
    url = wordlist_source_url(language)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": user_agent()},
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
    metadata_tmp = target.parent / f".lexhint-{os.getpid()}-{target.stem}.metadata.tmp"
    try:
        with gzip.open(tmp, "wt", encoding="utf-8", newline="\n") as handle:
            handle.write("\n".join(words))
            handle.write("\n")
        tmp.replace(target)
        metadata_tmp.write_text(
            json.dumps(_wordlist_metadata(language, words, url), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        metadata_tmp.replace(cached_wordlist_metadata_path(language))
    finally:
        tmp.unlink(missing_ok=True)
        metadata_tmp.unlink(missing_ok=True)
    return target
