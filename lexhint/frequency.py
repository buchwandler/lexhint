from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from .store import normalize_word

FREQUENCYWORDS_REVISION = "525f9b560de45753a5ea01069454e72e9aa541c6"


@dataclass(frozen=True, slots=True)
class FrequencyRow:
    word: str
    count: int
    rank: int


@dataclass(frozen=True, slots=True)
class FrequencyImportStats:
    rows: int
    matched_lexemes: int
    total_tokens: int


def iter_frequency_rows(lines: Iterable[str]) -> Iterator[FrequencyRow]:
    """Parse ordered ``WORD COUNT`` rows, preserving source rank."""
    seen: set[str] = set()
    for source_rank, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            word, raw_count = line.rsplit(maxsplit=1)
            count = int(raw_count)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"invalid frequency line: {raw_line.rstrip()!r}") from exc
        if count < 0:
            raise ValueError(f"frequency count must be non-negative: {raw_line.rstrip()!r}")
        normalized = normalize_word(word)
        if normalized and normalized not in seen:
            seen.add(normalized)
            yield FrequencyRow(normalized, count, source_rank)


def enrich_frequency(
    connection: sqlite3.Connection,
    rows: Iterable[FrequencyRow],
    *,
    batch_size: int = 10_000,
) -> FrequencyImportStats:
    """Update existing lexemes from streamed corpus rows without adding new ones."""
    imported = 0
    matched = 0
    total_tokens = 0
    batch: list[tuple[int, int, str]] = []

    def flush() -> None:
        nonlocal matched
        if not batch:
            return
        cursor = connection.executemany(
            "UPDATE lexemes SET corpus_count = ?, corpus_rank = ? WHERE word = ?",
            batch,
        )
        matched += cursor.rowcount
        connection.commit()
        batch.clear()

    for row in rows:
        imported += 1
        total_tokens += row.count
        batch.append((row.count, row.rank, row.word))
        if len(batch) >= batch_size:
            flush()
    flush()
    return FrequencyImportStats(imported, matched, total_tokens)


__all__ = [
    "FREQUENCYWORDS_REVISION",
    "FrequencyImportStats",
    "FrequencyRow",
    "enrich_frequency",
    "iter_frequency_rows",
]
