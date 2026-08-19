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
from .models import DictionaryBuildStats
from .store import (
    SCHEMA_VERSION,
    create_schema,
    iter_jsonl_entries,
    json_tuple,
    semantic_rows,
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
        request = urllib.request.Request(
            value,
            headers={"User-Agent": user_agent()},
        )
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
    timeout: float = 60.0,
    progress: Callable[[DictionaryBuildStats], None] | None = None,
) -> tuple[Path, DictionaryBuildStats]:
    """Build a compact dictionary-sense SQLite index from Wiktextract JSONL."""
    base_language = language.lower().split("-", 1)[0]
    target = Path(output) if output is not None else cached_dictionary_path(base_language)
    target = target.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    source_value = str(source)
    source_sha256 = _local_source_sha256(source)
    source_mode = "reproducible-full" if source_sha256 is not None else "live-full"
    snapshot_id = (
        f"sha256:{source_sha256}" if source_sha256 is not None else f"source:{source_value}"
    )

    fd, tmp_name = tempfile.mkstemp(prefix="lexhint-dict-", suffix=".sqlite3", dir=target.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    tmp.unlink(missing_ok=True)

    scanned = 0
    kept_entries = 0
    sense_count = 0
    seen_words: set[str] = set()

    try:
        connection = sqlite3.connect(tmp)
        try:
            create_schema(connection)
            set_metadata(
                connection,
                {
                    "schema_version": SCHEMA_VERSION,
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
                },
            )

            for entry in iter_wiktextract_entries(source, timeout=timeout):
                scanned += 1
                entry_kept = False
                for row in semantic_rows(entry, language=base_language):
                    cursor = connection.execute(
                        "INSERT OR IGNORE INTO senses("
                        "word, display_word, pos, glosses, topics"
                        ") VALUES (?, ?, ?, ?, ?)",
                        (
                            row.word,
                            row.display_word,
                            row.pos,
                            json_tuple(row.glosses),
                            json_tuple(row.topics),
                        ),
                    )
                    if cursor.rowcount:
                        entry_kept = True
                        sense_count += 1
                        seen_words.add(row.word)

                if entry_kept:
                    kept_entries += 1

                if scanned % 5000 == 0:
                    connection.commit()
                if progress is not None and scanned % 100_000 == 0:
                    progress(
                        DictionaryBuildStats(scanned, kept_entries, len(seen_words), sense_count)
                    )

            set_metadata(
                connection,
                {
                    "scanned_entries": str(scanned),
                    "kept_entries": str(kept_entries),
                    "words": str(len(seen_words)),
                    "senses": str(sense_count),
                },
            )
            connection.commit()
            if progress is not None:
                progress(DictionaryBuildStats(scanned, kept_entries, len(seen_words), sense_count))
            connection.execute("ANALYZE")
            connection.commit()
        finally:
            connection.close()
        tmp.replace(target)
    finally:
        tmp.unlink(missing_ok=True)

    return target, DictionaryBuildStats(scanned, kept_entries, len(seen_words), sense_count)
