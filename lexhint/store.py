from __future__ import annotations

import json
import sqlite3
import unicodedata
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .models import DictionaryEntry, Example, Form, Pronunciation

SCHEMA_VERSION = "7"
LEGACY_SCHEMA_VERSION = "6"
OLDER_LEGACY_SCHEMA_VERSION = "5"
OLDEST_LEGACY_SCHEMA_VERSION = "4"


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
    return tuple(dict.fromkeys(item for item in value if isinstance(item, str) and item))


def semantic_rows(entry: Mapping[str, object], *, language: str) -> Iterator[SemanticSenseRow]:
    from .extract import dictionary_entries

    for parsed in dictionary_entries(entry, language=language):
        for sense in parsed.senses:
            yield SemanticSenseRow(
                normalize_word(parsed.word), parsed.word, parsed.pos, sense.glosses, sense.topics
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
        [{"ipa": value.ipa, "tags": value.tags} for value in values],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _case_flags(display_word: str) -> tuple[bool, bool, bool]:
    cased = [character for character in display_word if character.isalpha()]
    if not cased:
        return False, False, False
    return (
        display_word == display_word.lower(),
        display_word == display_word.title(),
        display_word == display_word.upper(),
    )


def _has_table(connection: sqlite3.Connection, name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def insert_lexeme(connection: sqlite3.Connection, word: str, *, entry_count: int = 1) -> None:
    normalized = normalize_word(word)
    display = normalize_display_word(word)
    lower, title, upper = _case_flags(display)
    connection.execute(
        "INSERT INTO lexemes(word, entry_count, has_lowercase, has_titlecase, has_uppercase) "
        "VALUES (?, ?, ?, ?, ?) ON CONFLICT(word) DO UPDATE SET "
        "entry_count=entry_count + excluded.entry_count, "
        "has_lowercase=MAX(has_lowercase, excluded.has_lowercase), "
        "has_titlecase=MAX(has_titlecase, excluded.has_titlecase), "
        "has_uppercase=MAX(has_uppercase, excluded.has_uppercase)",
        (normalized, entry_count, lower, title, upper),
    )


def insert_dictionary_entries(
    connection: sqlite3.Connection, entries: Iterable[DictionaryEntry]
) -> tuple[int, int, set[str]]:
    entry_count = 0
    sense_count = 0
    words: set[str] = set()
    rich = _has_table(connection, "entries")
    for entry_index, entry in enumerate(entries):
        word = normalize_word(entry.word)
        display_word = normalize_display_word(entry.word)
        insert_lexeme(connection, display_word)
        words.add(word)
        entry_count += 1
        sense_count += len(entry.senses)
        if not rich:
            continue
        cursor = connection.execute(
            "INSERT INTO entries("
            "word, display_word, pos, entry_index, etymology, forms, pronunciations) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
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
        for sense_index, sense in enumerate(entry.senses):
            sense_cursor = connection.execute(
                "INSERT INTO senses("
                "entry_id, sense_index, glosses, topics, tags, examples, synonyms, antonyms) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
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
            assert sense_cursor.lastrowid is not None
            sense_id = sense_cursor.lastrowid
            if _has_table(connection, "sense_topics"):
                for topic in sense.topics:
                    connection.execute(
                        "INSERT INTO sense_topics(entry_id, sense_id, topic) VALUES (?, ?, ?)",
                        (entry_id, sense_id, topic),
                    )
    return entry_count, sense_count, words


def create_schema(
    connection: sqlite3.Connection,
    capabilities: Iterable[str] = ("lexical", "semantic", "dictionary"),
) -> None:
    selected = set(capabilities)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE lexemes (
            word TEXT PRIMARY KEY,
            entry_count INTEGER NOT NULL,
            has_lowercase INTEGER NOT NULL,
            has_titlecase INTEGER NOT NULL,
            has_uppercase INTEGER NOT NULL,
            corpus_count INTEGER,
            corpus_rank INTEGER
        );
        CREATE INDEX lexemes_corpus_rank_idx ON lexemes(corpus_rank);
        """
    )
    if "semantic" in selected:
        connection.executescript(
            """
            CREATE TABLE lexeme_domains (
                word TEXT NOT NULL,
                domain TEXT NOT NULL,
                weight REAL NOT NULL,
                source_topics TEXT NOT NULL,
                PRIMARY KEY(word, domain),
                FOREIGN KEY(word) REFERENCES lexemes(word)
            );
            CREATE INDEX lexeme_domains_domain_idx ON lexeme_domains(domain);
            """
        )
    if "dictionary" in selected:
        connection.executescript(
            """
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
            """
        )


def metadata(connection: sqlite3.Connection) -> dict[str, str]:
    return {
        str(row[0]): str(row[1]) for row in connection.execute("SELECT key, value FROM metadata")
    }


def set_metadata(connection: sqlite3.Connection, values: Mapping[str, str]) -> None:
    connection.executemany(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)", values.items()
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def initialize_partial(path: str | Path, language: str) -> Path:
    raise RuntimeError("partial runtime caches are no longer supported; rebuild the dictionary")


def dictionary_coverage(path: str | Path) -> str:
    with sqlite3.connect(path) as connection:
        row = connection.execute("SELECT value FROM metadata WHERE key='coverage'").fetchone()
    return "" if row is None else str(row[0])


def lookup_sense_count(path: str | Path, query: str) -> int:
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM senses AS s JOIN entries AS e ON e.id=s.entry_id "
            "WHERE e.display_word=?",
            (normalize_display_word(query),),
        ).fetchone()
    return 0 if row is None else int(row[0])


def lookup_status(path: str | Path, query: str) -> str | None:
    return None


def replace_word_entries(*args: object, **kwargs: object) -> int:
    raise RuntimeError("partial runtime caches are no longer supported; rebuild the dictionary")


def replace_word_rows(*args: object, **kwargs: object) -> int:
    raise RuntimeError("partial runtime caches are no longer supported; rebuild the dictionary")


def migrate_partial_v3_to_v4(path: str | Path) -> bool:
    raise RuntimeError("partial runtime caches are no longer supported; rebuild the dictionary")


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
