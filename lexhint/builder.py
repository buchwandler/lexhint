from __future__ import annotations

import gzip
import hashlib
import io
import os
import sqlite3
import tempfile
import urllib.request
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, TextIO
from urllib.parse import urlparse

from .download import cached_dictionary_path, package_version, user_agent
from .extract import dictionary_entries
from .frequency import FREQUENCYWORDS_REVISION, enrich_frequency, iter_frequency_rows
from .models import DictionaryBuildStats
from .store import (
    SCHEMA_VERSION,
    create_schema,
    insert_dictionary_entries,
    iter_jsonl_entries,
    set_metadata,
)

__all__ = ["SCHEMA_VERSION", "build_dictionary", "iter_wiktextract_entries"]


def _local_source_sha256(source: str | Path) -> str | None:
    value = Path(source).expanduser()
    if not value.is_file():
        return None
    digest = hashlib.sha256()
    with value.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@contextmanager
def _binary_source(source: str | Path, *, timeout: float) -> Iterator[BinaryIO]:
    value = str(source)
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"}:
        request = urllib.request.Request(value, headers={"User-Agent": user_agent()})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            yield response
        return
    with Path(value).expanduser().open("rb") as handle:
        yield handle


@contextmanager
def _text_source(source: str | Path, *, timeout: float = 60.0) -> Iterator[TextIO]:
    value = str(source)
    with _binary_source(source, timeout=timeout) as binary:
        if value.lower().endswith(".gz"):
            with (
                gzip.GzipFile(fileobj=binary, mode="rb") as decompressed,
                io.TextIOWrapper(decompressed, encoding="utf-8") as text,
            ):
                yield text
        else:
            with io.TextIOWrapper(binary, encoding="utf-8") as text:
                yield text


def iter_wiktextract_entries(
    source: str | Path, *, timeout: float = 60.0
) -> Iterator[dict[str, object]]:
    """Stream JSONL objects from a local path or HTTP(S) source."""
    with _text_source(source, timeout=timeout) as handle:
        yield from iter_jsonl_entries(handle)


def build_dictionary(
    language: str,
    source: str | Path,
    *,
    output: str | Path | None = None,
    frequency_source: str | Path | None = None,
    timeout: float = 60.0,
    progress: Callable[[DictionaryBuildStats], None] | None = None,
) -> tuple[Path, DictionaryBuildStats]:
    """Build a schema-6 dictionary SQLite index with optional frequency enrichment."""
    base_language = language.lower().split("-", 1)[0]
    target = Path(output) if output is not None else cached_dictionary_path(base_language)
    target = target.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    source_value = str(source)
    source_sha256 = _local_source_sha256(source)
    source_mode = "reproducible-full" if source_sha256 is not None else "live-full"
    frequency_value = str(frequency_source) if frequency_source is not None else ""
    frequency_sha256 = _local_source_sha256(frequency_source) if frequency_source else None
    identities = [value for value in (source_sha256, frequency_sha256) if value]
    if len(identities) == 2:
        snapshot_id = "sha256:" + ":".join(identities)
    elif identities:
        snapshot_id = "sha256:" + identities[0]
    else:
        snapshot_id = f"source:{source_value}"

    fd, tmp_name = tempfile.mkstemp(prefix="lexhint-dict-", suffix=".sqlite3", dir=target.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    tmp.unlink(missing_ok=True)

    scanned = 0
    kept_entries = 0
    sense_count = 0
    seen_words: set[str] = set()
    frequency_rows = 0
    frequency_matches = 0
    frequency_total_tokens = 0

    try:
        connection = sqlite3.connect(tmp)
        try:
            create_schema(connection)
            set_metadata(
                connection,
                {
                    "schema_version": SCHEMA_VERSION,
                    "dictionary_profile": "rich",
                    "language": base_language,
                    "coverage": "full",
                    "source_kind": "bulk",
                    "source": source_value,
                    "source_mode": source_mode,
                    "snapshot_id": snapshot_id,
                    "source_sha256": source_sha256 or "",
                    "built_at": datetime.now(timezone.utc).isoformat(),
                    "lexhint_version": package_version(),
                    "extractor_schema_version": SCHEMA_VERSION,
                    "frequency_source": "FrequencyWords" if frequency_source else "none",
                    "frequency_corpus": "OpenSubtitles2018" if frequency_source else "",
                    "frequency_source_revision": (
                        FREQUENCYWORDS_REVISION if frequency_source else ""
                    ),
                    "frequency_source_file": frequency_value,
                    "frequency_source_sha256": frequency_sha256 or "",
                },
            )

            for raw_entry in iter_wiktextract_entries(source, timeout=timeout):
                scanned += 1
                entries = tuple(dictionary_entries(raw_entry, language=base_language))
                if entries:
                    entry_count, inserted_senses, words = insert_dictionary_entries(
                        connection, entries
                    )
                    kept_entries += entry_count
                    sense_count += inserted_senses
                    seen_words.update(words)

                if scanned % 5000 == 0:
                    connection.commit()
                if progress is not None and scanned % 100_000 == 0:
                    progress(
                        DictionaryBuildStats(scanned, kept_entries, len(seen_words), sense_count)
                    )

            if frequency_source is not None:
                with _text_source(frequency_source, timeout=timeout) as handle:
                    frequency_stats = enrich_frequency(connection, iter_frequency_rows(handle))
                frequency_rows = frequency_stats.rows
                frequency_matches = frequency_stats.matched_lexemes
                frequency_total_tokens = frequency_stats.total_tokens

            set_metadata(
                connection,
                {
                    "scanned_entries": str(scanned),
                    "kept_entries": str(kept_entries),
                    "words": str(len(seen_words)),
                    "senses": str(sense_count),
                    "frequency_total_rows": str(frequency_rows),
                    "frequency_total_tokens": str(frequency_total_tokens),
                    "frequency_matched_lexemes": str(frequency_matches),
                },
            )
            connection.commit()
            final_stats = DictionaryBuildStats(
                scanned,
                kept_entries,
                len(seen_words),
                sense_count,
                frequency_rows,
                frequency_matches,
                frequency_total_tokens,
            )
            if progress is not None:
                progress(final_stats)
            connection.execute("ANALYZE")
            connection.commit()
        finally:
            connection.close()
        tmp.replace(target)
    finally:
        tmp.unlink(missing_ok=True)

    return target, final_stats
