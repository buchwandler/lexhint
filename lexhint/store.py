from __future__ import annotations

import json
import sqlite3
import unicodedata
from collections.abc import Iterable, Iterator, Mapping
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "4"
LEGACY_SCHEMA_VERSION = "3"


@dataclass(frozen=True, slots=True)
class SemanticSenseRow:
    word: str
    display_word: str
    pos: str
    glosses: tuple[str, ...]
    topics: tuple[str, ...]


def normalize_word(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def normalize_display_word(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    result: list[str] = []
    for item in value:
        if isinstance(item, str) and item and item not in result:
            result.append(item)
    return tuple(result)


def semantic_rows(entry: Mapping[str, object], *, language: str) -> Iterator[SemanticSenseRow]:
    base_language = language.lower().split("-", 1)[0]
    if str(entry.get("lang_code") or "").lower() != base_language:
        return

    display_word = normalize_display_word(str(entry.get("word") or ""))
    word = normalize_word(display_word)
    if not word:
        return

    pos = str(entry.get("pos") or "")
    entry_topics = strings(entry.get("topics"))
    senses = entry.get("senses")
    if not isinstance(senses, list):
        return

    for raw_sense in senses:
        if not isinstance(raw_sense, Mapping):
            continue
        glosses = strings(raw_sense.get("glosses"))
        topics = tuple(dict.fromkeys(entry_topics + strings(raw_sense.get("topics"))))
        if glosses or topics:
            yield SemanticSenseRow(word, display_word, pos, glosses, topics)


def json_tuple(values: tuple[str, ...]) -> str:
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE senses (
            id INTEGER PRIMARY KEY,
            word TEXT NOT NULL,
            display_word TEXT NOT NULL,
            pos TEXT NOT NULL,
            glosses TEXT NOT NULL,
            topics TEXT NOT NULL,
            UNIQUE(word, display_word, pos, glosses, topics)
        );
        CREATE INDEX senses_word_idx ON senses(word);
        CREATE INDEX senses_display_word_idx ON senses(display_word);
        CREATE TABLE lookups (
            query TEXT PRIMARY KEY,
            normalized TEXT NOT NULL,
            status TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            source_url TEXT NOT NULL
        );
        CREATE INDEX lookups_normalized_idx ON lookups(normalized);
        """
    )


def metadata(connection: sqlite3.Connection) -> dict[str, str]:
    return {
        str(row["key"] if isinstance(row, sqlite3.Row) else row[0]): str(
            row["value"] if isinstance(row, sqlite3.Row) else row[1]
        )
        for row in connection.execute("SELECT key, value FROM metadata")
    }


def set_metadata(connection: sqlite3.Connection, values: Mapping[str, str]) -> None:
    connection.executemany(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)", values.items()
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize_partial(path: str | Path, language: str) -> Path:
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return target
    connection = sqlite3.connect(target, timeout=30.0)
    try:
        create_schema(connection)
        set_metadata(
            connection,
            {
                "schema_version": SCHEMA_VERSION,
                "language": language.lower().split("-", 1)[0],
                "coverage": "partial",
                "source_kind": "kaikki-word",
            },
        )
        connection.commit()
    finally:
        connection.close()
    return target


def lookup_status(path: str | Path, query: str) -> str | None:
    normalized_query = normalize_display_word(query)
    with closing(sqlite3.connect(path)) as connection:
        row = connection.execute(
            "SELECT status FROM lookups WHERE query = ?", (normalized_query,)
        ).fetchone()
    return None if row is None else str(row[0])


def replace_word_rows(
    path: str | Path,
    *,
    language: str,
    query: str,
    source_url: str,
    entries: Iterable[Mapping[str, object]],
    status: str = "complete",
) -> int:
    normalized_query = normalize_display_word(query)
    rows: list[SemanticSenseRow] = []
    for entry in entries:
        rows.extend(semantic_rows(entry, language=language))

    connection = sqlite3.connect(path, timeout=30.0)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM senses WHERE display_word = ?", (normalized_query,))
        connection.executemany(
            "INSERT OR IGNORE INTO senses("
            "word, display_word, pos, glosses, topics"
            ") VALUES (?, ?, ?, ?, ?)",
            [
                (
                    row.word,
                    row.display_word,
                    row.pos,
                    json_tuple(row.glosses),
                    json_tuple(row.topics),
                )
                for row in rows
            ],
        )
        connection.execute(
            "INSERT OR REPLACE INTO lookups("
            "query, normalized, status, fetched_at, source_url"
            ") VALUES (?, ?, ?, ?, ?)",
            (normalized_query, normalize_word(normalized_query), status, utc_now(), source_url),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return len(rows)


def dictionary_coverage(path: str | Path) -> str:
    with closing(sqlite3.connect(path)) as connection:
        row = connection.execute("SELECT value FROM metadata WHERE key = 'coverage'").fetchone()
    return "" if row is None else str(row[0])


def lookup_sense_count(path: str | Path, query: str) -> int:
    with closing(sqlite3.connect(path)) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM senses WHERE display_word = ?",
            (normalize_display_word(query),),
        ).fetchone()
    return 0 if row is None else int(row[0])


def migrate_partial_v3_to_v4(path: str | Path) -> bool:
    with closing(sqlite3.connect(path, timeout=30.0)) as connection:
        actual = metadata(connection)
        if actual.get("schema_version") != LEGACY_SCHEMA_VERSION:
            return False
        if actual.get("coverage") != "partial":
            return False

        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM senses")
        connection.execute("DELETE FROM lookups")
        set_metadata(connection, {"schema_version": SCHEMA_VERSION})
        connection.commit()
    return True


def iter_jsonl_entries(lines: Iterable[str]) -> Iterator[dict[str, object]]:
    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            value = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL at line {line_number}: {exc}") from exc
        if isinstance(value, dict):
            yield value
