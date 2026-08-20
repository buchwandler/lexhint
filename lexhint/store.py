from __future__ import annotations

import json
import sqlite3
import unicodedata
from collections.abc import Iterable, Iterator, Mapping
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .models import DictionaryEntry, Example, Form, Pronunciation

SCHEMA_VERSION = "5"
LEGACY_SCHEMA_VERSION = "4"
OLDER_LEGACY_SCHEMA_VERSION = "3"


@dataclass(frozen=True, slots=True)
class SemanticSenseRow:
    """Compatibility projection of one rich sense for semantic callers."""

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
    from .extract import dictionary_entries

    for parsed in dictionary_entries(entry, language=language):
        for sense in parsed.senses:
            yield SemanticSenseRow(
                normalize_word(parsed.word),
                parsed.word,
                parsed.pos,
                sense.glosses,
                sense.topics,
            )


def json_tuple(values: tuple[str, ...]) -> str:
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


def _json_examples(values: tuple[Example, ...]) -> str:
    return json.dumps(
        [{"text": value.text, "translation": value.translation} for value in values],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _json_forms(values: tuple[Form, ...]) -> str:
    return json.dumps(
        [{"form": value.form, "tags": value.tags} for value in values],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _json_pronunciations(values: tuple[Pronunciation, ...]) -> str:
    return json.dumps(
        [{"ipa": value.ipa, "audio": value.audio, "tags": value.tags} for value in values],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def insert_dictionary_entries(
    connection: sqlite3.Connection, entries: Iterable[DictionaryEntry]
) -> tuple[int, int, set[str]]:
    entry_count = 0
    sense_count = 0
    words: set[str] = set()
    for entry_index, entry in enumerate(entries):
        word = normalize_word(entry.word)
        display_word = normalize_display_word(entry.word)
        cursor = connection.execute(
            "INSERT INTO entries("
            "word, display_word, pos, entry_index, etymology, forms, pronunciations"
            ") VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                word,
                display_word,
                entry.pos,
                entry_index,
                entry.etymology or "",
                _json_forms(entry.forms),
                _json_pronunciations(entry.pronunciations),
            ),
        )
        assert cursor.lastrowid is not None
        entry_id = cursor.lastrowid
        entry_count += 1
        words.add(word)
        for sense_index, sense in enumerate(entry.senses):
            cursor = connection.execute(
                "INSERT INTO senses("
                "entry_id, sense_index, glosses, topics, tags, examples, synonyms, antonyms"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entry_id,
                    sense_index,
                    json_tuple(sense.glosses),
                    json_tuple(sense.topics),
                    json_tuple(sense.tags),
                    _json_examples(sense.examples),
                    json_tuple(sense.synonyms),
                    json_tuple(sense.antonyms),
                ),
            )
            assert cursor.lastrowid is not None
            sense_id = cursor.lastrowid
            for topic in sense.topics:
                connection.execute(
                    "INSERT INTO sense_topics(entry_id, sense_id, topic) VALUES (?, ?, ?)",
                    (entry_id, sense_id, topic),
                )
            sense_count += 1
    return entry_count, sense_count, words


def create_schema(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE entries (
            id INTEGER PRIMARY KEY,
            word TEXT NOT NULL,
            display_word TEXT NOT NULL,
            pos TEXT NOT NULL,
            entry_index INTEGER NOT NULL,
            etymology TEXT NOT NULL DEFAULT '',
            forms TEXT NOT NULL DEFAULT '[]',
            pronunciations TEXT NOT NULL DEFAULT '[]'
        );
        CREATE INDEX entries_word_idx ON entries(word);
        CREATE INDEX entries_display_word_idx ON entries(display_word);
        CREATE TABLE senses (
            id INTEGER PRIMARY KEY,
            entry_id INTEGER NOT NULL,
            sense_index INTEGER NOT NULL,
            glosses TEXT NOT NULL,
            topics TEXT NOT NULL,
            tags TEXT NOT NULL,
            examples TEXT NOT NULL,
            synonyms TEXT NOT NULL,
            antonyms TEXT NOT NULL,
            FOREIGN KEY(entry_id) REFERENCES entries(id) ON DELETE CASCADE
        );
        CREATE INDEX senses_entry_idx ON senses(entry_id);
        CREATE TABLE sense_topics (
            entry_id INTEGER NOT NULL,
            sense_id INTEGER NOT NULL,
            topic TEXT NOT NULL,
            FOREIGN KEY(entry_id) REFERENCES entries(id) ON DELETE CASCADE,
            FOREIGN KEY(sense_id) REFERENCES senses(id) ON DELETE CASCADE
        );
        CREATE INDEX sense_topics_topic_idx ON sense_topics(topic);
        CREATE INDEX sense_topics_entry_idx ON sense_topics(entry_id);
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
                "dictionary_profile": "rich",
                "language": language.lower().split("-", 1)[0],
                "coverage": "partial",
                "source_kind": "kaikki-word",
                "source_mode": "live-partial",
                "snapshot_id": "partial-cache",
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


def replace_word_entries(
    path: str | Path,
    *,
    language: str,
    query: str,
    source_url: str,
    entries: Iterable[DictionaryEntry],
    status: str = "complete",
) -> int:
    normalized_query = normalize_display_word(query)
    entries_value = tuple(entries)
    connection = sqlite3.connect(path, timeout=30.0)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DELETE FROM entries WHERE display_word = ?", (normalized_query,))
        _, sense_count, _ = insert_dictionary_entries(connection, entries_value)
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
    return sense_count


def replace_word_rows(
    path: str | Path,
    *,
    language: str,
    query: str,
    source_url: str,
    entries: Iterable[Mapping[str, object]],
    status: str = "complete",
) -> int:
    from .extract import dictionary_entries

    rich_entries = tuple(
        parsed
        for raw_entry in entries
        for parsed in dictionary_entries(raw_entry, language=language)
    )
    return replace_word_entries(
        path,
        language=language,
        query=query,
        source_url=source_url,
        entries=rich_entries,
        status=status,
    )


def dictionary_coverage(path: str | Path) -> str:
    with closing(sqlite3.connect(path)) as connection:
        row = connection.execute("SELECT value FROM metadata WHERE key = 'coverage'").fetchone()
    return "" if row is None else str(row[0])


def lookup_sense_count(path: str | Path, query: str) -> int:
    with closing(sqlite3.connect(path)) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM senses AS s JOIN entries AS e ON e.id = s.entry_id "
            "WHERE e.display_word = ?",
            (normalize_display_word(query),),
        ).fetchone()
    return 0 if row is None else int(row[0])


def migrate_partial_v3_to_v4(path: str | Path) -> bool:
    """Invalidate a legacy partial cache whose rows cannot form rich entries."""
    with closing(sqlite3.connect(path, timeout=30.0)) as connection:
        actual = metadata(connection)
        if (
            actual.get("schema_version")
            not in {
                LEGACY_SCHEMA_VERSION,
                OLDER_LEGACY_SCHEMA_VERSION,
            }
            or actual.get("coverage") != "partial"
        ):
            return False

        language = actual.get("language", "")
        connection.execute("PRAGMA foreign_keys = OFF")
        for table in ("sense_topics", "senses", "entries", "lookups", "metadata"):
            connection.execute(f"DROP TABLE IF EXISTS {table}")  # noqa: S608
        create_schema(connection)
        set_metadata(
            connection,
            {
                "schema_version": SCHEMA_VERSION,
                "dictionary_profile": "rich",
                "language": language,
                "coverage": "partial",
                "source_kind": "kaikki-word",
                "source_mode": "live-partial",
                "snapshot_id": "partial-cache",
            },
        )
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
