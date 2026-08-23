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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, TextIO, cast
from urllib.parse import urlparse

from .download import cached_dictionary_path, package_version, user_agent
from .extract import dictionary_entries
from .frequency import enrich_frequency, iter_frequency_rows
from .languages import normalize_language
from .models import DictionaryBuildStats
from .schema import CapabilitySelection, normalize_capabilities
from .semantics import insert_lexeme_domains
from .sources import ResolvedFrequencySource, resolve_frequency_source
from .store import (
    SCHEMA_VERSION,
    create_schema,
    insert_dictionary_entries,
    insert_lexeme_search_index,
    iter_jsonl_entries,
    set_metadata,
)

__all__ = [
    "SCHEMA_VERSION",
    "BuildPlan",
    "build_dictionary",
    "iter_wiktextract_entries",
    "project_artifact",
    "prepare_build_plan",
]


@dataclass(frozen=True, slots=True)
class BuildPlan:
    language: str
    source: str | Path
    output: Path
    capabilities: tuple[str, ...]
    profile: str
    frequency_mode: str
    frequency_source: str | Path | None
    refresh_frequency: bool
    offline: bool
    timeout: float
    resolved_frequency: ResolvedFrequencySource | None


def _sha256(source: str | Path) -> str | None:
    path = Path(source).expanduser()
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class _DigestingReader:
    def __init__(self, stream: BinaryIO, digest: Any) -> None:
        self._stream = stream
        self._digest = digest

    def read(self, size: int = -1) -> bytes:
        data = self._stream.read(size)
        self._digest.update(data)
        return data

    def readinto(self, buffer: Any) -> int | None:
        stream = cast(Any, self._stream)
        count = cast(int | None, stream.readinto(buffer))
        if count:
            self._digest.update(memoryview(buffer)[:count])
        return count

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)


@contextmanager
def _binary_source(
    source: str | Path, *, timeout: float, offline: bool = False, digest: Any = None
) -> Iterator[BinaryIO]:
    value = str(source)
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"}:
        if offline:
            raise OSError("HTTP dictionary sources are unavailable in offline mode")
        request = urllib.request.Request(value, headers={"User-Agent": user_agent()})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            stream = _DigestingReader(response, digest) if digest is not None else response
            yield cast(BinaryIO, stream)
        return
    with Path(value).expanduser().open("rb") as handle:
        yield handle


@contextmanager
def _text_source(
    source: str | Path,
    *,
    timeout: float = 60.0,
    offline: bool = False,
    digest: Any = None,
) -> Iterator[TextIO]:
    value = str(source)
    with _binary_source(source, timeout=timeout, offline=offline, digest=digest) as binary:
        if value.lower().endswith(".gz") or urlparse(value).path.lower().endswith(".gz"):
            with (
                gzip.GzipFile(fileobj=binary, mode="rb") as decompressed,
                io.TextIOWrapper(decompressed, encoding="utf-8") as text,
            ):
                yield text
        else:
            with io.TextIOWrapper(binary, encoding="utf-8") as text:
                yield text


def iter_wiktextract_entries(
    source: str | Path,
    *,
    timeout: float = 60.0,
    offline: bool = False,
    digest: Any = None,
) -> Iterator[dict[str, object]]:
    with _text_source(source, timeout=timeout, offline=offline, digest=digest) as handle:
        yield from iter_jsonl_entries(handle)


def _profile(selection: CapabilitySelection) -> str:
    return selection.profile


def prepare_build_plan(
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
) -> BuildPlan:
    if no_frequency and frequency_source is not None:
        raise ValueError("--no-frequency cannot be combined with --frequency-source")
    if no_frequency and refresh_frequency:
        raise ValueError("--no-frequency cannot be combined with --refresh-frequency")
    if frequency_source is not None and refresh_frequency:
        raise ValueError("--frequency-source cannot be combined with --refresh-frequency")
    source_value = str(source)
    if offline and urlparse(source_value).scheme in {"http", "https"}:
        raise OSError("HTTP dictionary sources are unavailable in offline mode")
    selection = normalize_capabilities(capabilities, profile=profile)
    base_language = normalize_language(language)
    resolved_frequency = resolve_frequency_source(
        base_language,
        source=frequency_source,
        enabled=not no_frequency,
        refresh=refresh_frequency,
        offline=offline,
        timeout=timeout,
    )
    target = Path(output) if output is not None else cached_dictionary_path(base_language)
    return BuildPlan(
        base_language,
        source,
        target.expanduser(),
        selection.capabilities,
        selection.profile,
        "disabled" if no_frequency else "custom" if frequency_source is not None else "auto",
        frequency_source,
        refresh_frequency,
        offline,
        timeout,
        resolved_frequency,
    )


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
    plan = prepare_build_plan(
        language,
        source,
        output=output,
        capabilities=capabilities,
        profile=profile,
        frequency_source=frequency_source,
        no_frequency=no_frequency,
        refresh_frequency=refresh_frequency,
        offline=offline,
        timeout=timeout,
    )
    target = plan.output
    target.parent.mkdir(parents=True, exist_ok=True)
    source_value = str(plan.source)
    source_sha256 = _sha256(plan.source)
    source_digest = hashlib.sha256() if urlparse(source_value).scheme in {"http", "https"} else None
    selection = CapabilitySelection(plan.capabilities, plan.profile)
    base_language = plan.language
    resolved_frequency = plan.resolved_frequency
    fd, tmp_name = tempfile.mkstemp(prefix="lexhint-dict-", suffix=".sqlite3", dir=target.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    tmp.unlink(missing_ok=True)

    scanned = kept_entries = sense_count = 0
    frequency_rows = frequency_matches = frequency_total_tokens = 0
    semantic_rows = 0
    search_lexeme_rows = search_sense_rows = 0
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
            for raw_entry in iter_wiktextract_entries(
                plan.source,
                timeout=plan.timeout,
                offline=plan.offline,
                digest=source_digest,
            ):
                scanned += 1
                entries = tuple(dictionary_entries(raw_entry, language=base_language))
                if entries:
                    entry_count, inserted_senses, _words = insert_dictionary_entries(
                        connection, entries
                    )
                    if "search" in selection.capabilities:
                        insert_lexeme_search_index(connection, _words)
                    kept_entries += entry_count
                    sense_count += inserted_senses
                    if "semantic" in selection.capabilities:
                        for entry in entries:
                            insert_lexeme_domains(
                                connection,
                                {
                                    entry.word: (
                                        topic for sense in entry.senses for topic in sense.topics
                                    )
                                },
                            )
                if scanned % 5000 == 0:
                    connection.commit()
                if progress is not None and scanned % 25_000 == 0:
                    lexeme_count = int(
                        connection.execute("SELECT COUNT(*) FROM lexemes").fetchone()[0]
                    )
                    progress(
                        DictionaryBuildStats(
                            base_language,
                            selection.capabilities,
                            scanned,
                            kept_entries,
                            lexeme_count,
                            sense_count,
                        )
                    )

            if source_digest is not None:
                source_sha256 = source_digest.hexdigest()
                set_metadata(
                    connection,
                    {
                        "dictionary_source_sha256": source_sha256,
                        "source_sha256": source_sha256,
                    },
                )
            if "semantic" in selection.capabilities:
                semantic_rows = int(
                    connection.execute("SELECT COUNT(*) FROM lexeme_domains").fetchone()[0]
                )
            if "search" in selection.capabilities:
                search_lexeme_rows = int(
                    connection.execute("SELECT COUNT(*) FROM lexeme_ngrams").fetchone()[0]
                )
                if "dictionary" in selection.capabilities:
                    search_sense_rows = int(
                        connection.execute("SELECT COUNT(*) FROM sense_search_terms").fetchone()[0]
                    )
            if resolved_frequency is not None:
                with _text_source(
                    resolved_frequency.path, timeout=plan.timeout, offline=plan.offline
                ) as handle:
                    imported = enrich_frequency(connection, iter_frequency_rows(handle))
                frequency_rows = imported.rows
                frequency_matches = imported.matched_lexemes
                frequency_total_tokens = imported.total_tokens
            lexeme_count = int(connection.execute("SELECT COUNT(*) FROM lexemes").fetchone()[0])
            set_metadata(
                connection,
                {
                    "scanned_entries": str(scanned),
                    "kept_entries": str(kept_entries),
                    "words": str(lexeme_count),
                    "lexemes": str(lexeme_count),
                    "senses": str(sense_count),
                    "entry_count": str(
                        kept_entries if "dictionary" in selection.capabilities else 0
                    ),
                    "sense_count": str(
                        sense_count if "dictionary" in selection.capabilities else 0
                    ),
                    "search_index_version": "1" if "search" in selection.capabilities else "",
                    "search_lexeme_ngram_rows": str(search_lexeme_rows),
                    "search_sense_term_rows": str(search_sense_rows),
                    "semantic_lexeme_count": str(semantic_rows),
                    "frequency_total_rows": str(frequency_rows),
                    "frequency_total_tokens": str(frequency_total_tokens),
                    "frequency_matched_lexemes": str(frequency_matches),
                },
            )
            connection.commit()
            lexeme_count = int(connection.execute("SELECT COUNT(*) FROM lexemes").fetchone()[0])
            final_stats = DictionaryBuildStats(
                base_language,
                selection.capabilities,
                scanned,
                kept_entries,
                lexeme_count,
                sense_count,
                semantic_rows,
                frequency_rows,
                frequency_matches,
                frequency_total_tokens,
                kept_entries if "dictionary" in selection.capabilities else 0,
                search_lexeme_rows=search_lexeme_rows,
                search_sense_rows=search_sense_rows,
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
        if resolved_frequency is not None and resolved_frequency.temporary:
            resolved_frequency.path.unlink(missing_ok=True)
    return target, final_stats


def project_artifact(
    source: str | Path,
    *,
    output: str | Path,
    capabilities: str | tuple[str, ...] | None = None,
    profile: str | None = None,
) -> Path:
    """Create a fresh capability subset artifact from a full Lexhint artifact."""
    from .lexicon import Lexicon

    source_path = Path(source).expanduser().resolve()
    output_path = Path(output).expanduser()
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    if output_path.exists() and output_path.resolve() == source_path:
        raise ValueError("projection output must differ from source artifact")

    source_lexicon = Lexicon.from_path(source_path)
    if source_lexicon.metadata.get("coverage") != "full":
        raise ValueError("projection requires a full-coverage source artifact")
    selection = normalize_capabilities(capabilities, profile=profile)
    source_capabilities = source_lexicon.capabilities
    if not set(selection.capabilities).issubset(source_capabilities):
        raise ValueError("projection capabilities must be a subset of source capabilities")

    digest = hashlib.sha256()
    with source_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix="lexhint-project-", suffix=".sqlite3", dir=output_path.parent
    )
    os.close(fd)
    temporary = Path(temporary_name)
    source_connection = source_lexicon._connect()
    target_connection: sqlite3.Connection | None = None
    try:
        target_connection = sqlite3.connect(temporary)
        create_schema(target_connection, selection.capabilities)
        target_connection.executemany(
            "INSERT INTO lexemes("
            "word, entry_count, has_lowercase, has_titlecase, has_uppercase, "
            "corpus_count, corpus_rank) VALUES (?, ?, ?, ?, ?, ?, ?)",
            source_connection.execute(
                "SELECT word, entry_count, has_lowercase, has_titlecase, has_uppercase, "
                "corpus_count, corpus_rank FROM lexemes"
            ).fetchall(),
        )
        if "search" in selection.capabilities:
            target_connection.executemany(
                "INSERT INTO lexeme_ngrams(gram, word) VALUES (?, ?)",
                source_connection.execute("SELECT gram, word FROM lexeme_ngrams").fetchall(),
            )
        if "semantic" in selection.capabilities:
            target_connection.executemany(
                "INSERT INTO lexeme_domains(word, domain, weight, source_topics) "
                "VALUES (?, ?, ?, ?)",
                source_connection.execute(
                    "SELECT word, domain, weight, source_topics FROM lexeme_domains"
                ).fetchall(),
            )
        if "dictionary" in selection.capabilities:
            for table, columns in (
                (
                    "entries",
                    "id, word, display_word, pos, entry_index, etymology, forms, pronunciations",
                ),
                (
                    "senses",
                    "id, entry_id, sense_index, glosses, topics, tags, examples, "
                    "synonyms, antonyms",
                ),
                ("sense_topics", "entry_id, sense_id, topic"),
            ):
                placeholders = ", ".join("?" for _ in columns.split(", "))
                target_connection.executemany(
                    f"INSERT INTO {table}({columns}) VALUES ({placeholders})",
                    source_connection.execute(f"SELECT {columns} FROM {table}").fetchall(),
                )
            if "search" in selection.capabilities:
                target_connection.executemany(
                    "INSERT INTO sense_search_terms(term, sense_id, field, term_count) "
                    "VALUES (?, ?, ?, ?)",
                    source_connection.execute(
                        "SELECT term, sense_id, field, term_count FROM sense_search_terms"
                    ).fetchall(),
                )
        metadata = dict(source_lexicon.metadata)
        if "search" in selection.capabilities:
            metadata_search_rows = int(
                target_connection.execute("SELECT COUNT(*) FROM lexeme_ngrams").fetchone()[0]
            )
            metadata_sense_rows = (
                int(
                    target_connection.execute("SELECT COUNT(*) FROM sense_search_terms").fetchone()[
                        0
                    ]
                )
                if "dictionary" in selection.capabilities
                else 0
            )
        else:
            metadata_search_rows = metadata_sense_rows = 0
            for key in (
                "search_index_version",
                "search_lexeme_ngram_rows",
                "search_sense_term_rows",
            ):
                metadata.pop(key, None)
        now = datetime.now(timezone.utc).isoformat()
        metadata.update(
            {
                "profile": selection.profile,
                "dictionary_profile": selection.profile,
                "capabilities": ",".join(selection.capabilities),
                "search_index_version": ("1" if "search" in selection.capabilities else ""),
                "search_lexeme_ngram_rows": str(metadata_search_rows),
                "search_sense_term_rows": str(metadata_sense_rows),
                "created_at": now,
                "built_at": now,
                "projected_from_sha256": digest.hexdigest(),
                "projected_from_capabilities": ",".join(source_capabilities),
                "projected_from_profile": source_lexicon.metadata.get("profile", ""),
            }
        )
        if "search" not in selection.capabilities:
            for key in (
                "search_index_version",
                "search_lexeme_ngram_rows",
                "search_sense_term_rows",
            ):
                metadata.pop(key, None)
        set_metadata(target_connection, metadata)
        target_connection.execute("ANALYZE")
        target_connection.commit()
        if target_connection.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise sqlite3.DatabaseError("projected artifact failed PRAGMA quick_check")
    finally:
        source_connection.close()
        if target_connection is not None:
            target_connection.close()
    try:
        temporary.replace(output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return output_path
