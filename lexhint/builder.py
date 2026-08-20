from __future__ import annotations

import gzip
import hashlib
import io
import os
import sqlite3
import tempfile
import urllib.request
from collections import defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, TextIO
from urllib.parse import urlparse

from .download import cached_dictionary_path, package_version, user_agent
from .extract import dictionary_entries
from .frequency import enrich_frequency, iter_frequency_rows
from .models import DictionaryBuildStats
from .schema import CapabilitySelection, normalize_capabilities
from .semantics import insert_lexeme_domains
from .sources import resolve_frequency_source
from .store import (
    SCHEMA_VERSION,
    create_schema,
    insert_dictionary_entries,
    iter_jsonl_entries,
    set_metadata,
)

__all__ = ["SCHEMA_VERSION", "build_dictionary", "iter_wiktextract_entries"]


def _sha256(source: str | Path) -> str | None:
    path = Path(source).expanduser()
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
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
    with _text_source(source, timeout=timeout) as handle:
        yield from iter_jsonl_entries(handle)


def _profile(selection: CapabilitySelection) -> str:
    return selection.profile


def build_dictionary(
    language: str,
    source: str | Path,
    *,
    output: str | Path | None = None,
    capabilities: str | tuple[str, ...] | None = None,
    profile: str | None = None,
    frequency_source: str | Path | None = None,
    no_frequency: bool = False,
    refresh_frequency: bool = False,
    offline: bool = False,
    timeout: float = 60.0,
    progress: Callable[[DictionaryBuildStats], None] | None = None,
) -> tuple[Path, DictionaryBuildStats]:
    if no_frequency and frequency_source is not None:
        raise ValueError("--no-frequency cannot be combined with --frequency-source")
    if no_frequency and refresh_frequency:
        raise ValueError("--no-frequency cannot be combined with --refresh-frequency")
    if frequency_source is not None and refresh_frequency:
        raise ValueError("--frequency-source cannot be combined with --refresh-frequency")
    selection = normalize_capabilities(capabilities, profile=profile)
    base_language = language.lower().split("-", 1)[0]
    resolved_frequency = resolve_frequency_source(
        base_language,
        source=frequency_source,
        enabled=not no_frequency,
        refresh=refresh_frequency,
        offline=offline,
        timeout=timeout,
    )
    target = Path(output) if output is not None else cached_dictionary_path(base_language)
    target = target.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    source_value = str(source)
    source_sha256 = _sha256(source)
    fd, tmp_name = tempfile.mkstemp(prefix="lexhint-dict-", suffix=".sqlite3", dir=target.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    tmp.unlink(missing_ok=True)

    scanned = kept_entries = sense_count = 0
    seen_words: set[str] = set()
    domains_by_word: dict[str, set[str]] = defaultdict(set)
    frequency_rows = frequency_matches = frequency_total_tokens = 0
    semantic_rows = 0
    final_stats: DictionaryBuildStats
    try:
        connection = sqlite3.connect(tmp)
        try:
            create_schema(connection, selection.capabilities)
            set_metadata(
                connection,
                {
                    "schema_version": SCHEMA_VERSION,
                    "language": base_language,
                    "coverage": "full",
                    "profile": _profile(selection),
                    "dictionary_profile": _profile(selection),
                    "capabilities": ",".join(selection.capabilities),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "built_at": datetime.now(timezone.utc).isoformat(),
                    "builder_version": package_version(),
                    "lexhint_version": package_version(),
                    "dictionary_source": source_value,
                    "dictionary_source_sha256": source_sha256 or "",
                    "source": source_value,
                    "source_sha256": source_sha256 or "",
                    "frequency_source": resolved_frequency.provider
                    if resolved_frequency
                    else "none",
                    "frequency_corpus": resolved_frequency.corpus if resolved_frequency else "",
                    "frequency_source_revision": resolved_frequency.revision
                    if resolved_frequency
                    else "",
                    "frequency_source_url": resolved_frequency.source_url
                    if resolved_frequency
                    else "",
                    "frequency_source_sha256": resolved_frequency.sha256
                    if resolved_frequency
                    else "",
                    "frequency_source_file": str(resolved_frequency.path)
                    if resolved_frequency
                    else "",
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
                    if "semantic" in selection.capabilities:
                        for entry in entries:
                            domains_by_word[entry.word].update(
                                topic for sense in entry.senses for topic in sense.topics
                            )
                if scanned % 5000 == 0:
                    connection.commit()
                if progress is not None and scanned % 100_000 == 0:
                    progress(
                        DictionaryBuildStats(
                            base_language,
                            selection.capabilities,
                            scanned,
                            kept_entries,
                            len(seen_words),
                            sense_count,
                        )
                    )

            if "semantic" in selection.capabilities:
                semantic_rows = insert_lexeme_domains(connection, domains_by_word)
            if resolved_frequency is not None:
                with _text_source(resolved_frequency.path, timeout=timeout) as handle:
                    imported = enrich_frequency(connection, iter_frequency_rows(handle))
                frequency_rows = imported.rows
                frequency_matches = imported.matched_lexemes
                frequency_total_tokens = imported.total_tokens
            set_metadata(
                connection,
                {
                    "scanned_entries": str(scanned),
                    "kept_entries": str(kept_entries),
                    "words": str(len(seen_words)),
                    "lexemes": str(len(seen_words)),
                    "senses": str(sense_count),
                    "entry_count": str(
                        kept_entries if "dictionary" in selection.capabilities else 0
                    ),
                    "sense_count": str(
                        sense_count if "dictionary" in selection.capabilities else 0
                    ),
                    "semantic_lexeme_count": str(semantic_rows),
                    "frequency_total_rows": str(frequency_rows),
                    "frequency_total_tokens": str(frequency_total_tokens),
                    "frequency_matched_lexemes": str(frequency_matches),
                },
            )
            connection.commit()
            final_stats = DictionaryBuildStats(
                base_language,
                selection.capabilities,
                scanned,
                kept_entries,
                len(seen_words),
                sense_count,
                semantic_rows,
                frequency_rows,
                frequency_matches,
                frequency_total_tokens,
                kept_entries if "dictionary" in selection.capabilities else 0,
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
