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
from .models import DictionaryBuildStats
from .schema import CapabilitySelection, normalize_capabilities
from .semantics import insert_lexeme_domains
from .sources import ResolvedFrequencySource, resolve_frequency_source
from .store import (
    SCHEMA_VERSION,
    create_schema,
    insert_dictionary_entries,
    iter_jsonl_entries,
    set_metadata,
)

__all__ = [
    "SCHEMA_VERSION",
    "BuildPlan",
    "build_dictionary",
    "iter_wiktextract_entries",
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
