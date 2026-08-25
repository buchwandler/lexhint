from __future__ import annotations

import base64
import binascii
import hashlib
import json
import sqlite3
import unicodedata
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field

from .languages import normalize_language
from .models import (
    DictionaryEntry,
    Example,
    ExternalSenseId,
    Form,
    HeadwordRelation,
    Pronunciation,
    RelatedTerm,
    Sense,
)
from .schema_contract import (
    SCHEMA_VERSION as _SCHEMA_VERSION,
)
from .schema_contract import (
    SQLITE_APPLICATION_ID,
    SQLITE_USER_VERSION,
    SchemaContractError,
    canonical_capabilities,
    validate_artifact_structure,
)
from .search import search_tokens, word_ngrams

SCHEMA_VERSION = _SCHEMA_VERSION
MAX_STABLE_SENSE_ID = (1 << 63) - 1


class SenseIdentityCollision(ValueError):
    """Two different source senses produced the same deterministic ID."""


@dataclass(slots=True)
class SenseIdentityRegistry:
    counts: dict[bytes, int] = field(default_factory=dict)
    ids: dict[int, bytes] = field(default_factory=dict)


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


def _identity_text(value: str) -> str:
    return unicodedata.normalize("NFC", value).strip()


def sense_identity_anchor(
    language: str,
    entry: DictionaryEntry,
    sense: Sense,
    duplicate_index: int = 0,
) -> bytes:
    source_ids = tuple(sorted((item.namespace, item.value) for item in sense.source_ids))
    payload: dict[str, object] = {
        "v": 1,
        "language": normalize_language(language),
        "word": normalize_word(entry.word),
        "pos": normalize_word(entry.pos),
        "etymology_number": entry.etymology_number or "",
        "source_ids": source_ids,
        "duplicate": duplicate_index,
    }
    if not source_ids:
        payload["glosses"] = tuple(sorted(_identity_text(value) for value in sense.glosses))
        payload["identity_tags"] = tuple(sorted(sense.tags))
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def stable_sense_int(anchor: bytes) -> int:
    digest = hashlib.blake2b(anchor, digest_size=8, person=b"lexhint1").digest()
    value = int.from_bytes(digest, "big") & MAX_STABLE_SENSE_ID
    return value or 1


def format_sense_id(language: str, value: int) -> str:
    if not 1 <= value <= MAX_STABLE_SENSE_ID:
        raise ValueError("sense integer ID is outside the positive 63-bit range")
    encoded = base64.b32encode(value.to_bytes(8, "big")).decode("ascii").rstrip("=")
    return f"lh1-{normalize_language(language)}-{encoded}"


def parse_sense_id(language: str, value: str) -> int | None:
    parts = value.split("-", 2)
    if len(parts) != 3 or parts[0] != "lh1" or parts[1] != normalize_language(language):
        return None
    encoded = parts[2].upper()
    try:
        padded = encoded + "=" * ((8 - len(encoded) % 8) % 8)
        raw = base64.b32decode(padded, casefold=True)
    except (ValueError, binascii.Error):
        return None
    if len(raw) != 8:
        return None
    result = int.from_bytes(raw, "big")
    return result if 1 <= result <= MAX_STABLE_SENSE_ID else None


def _json_source_ids(values: tuple[ExternalSenseId, ...]) -> str:
    return json.dumps(
        [{"namespace": value.namespace, "value": value.value} for value in values],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _json_examples(values: tuple[Example, ...]) -> str:
    return json.dumps(
        [
            {
                "text": value.text,
                "translation": value.translation,
                **({"kind": value.kind} if value.kind is not None else {}),
            }
            for value in values
        ],
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


def _json_related(values: tuple[str | RelatedTerm, ...]) -> str:
    return json.dumps(
        [
            value
            if isinstance(value, str)
            else {"word": value.word, "relation": value.relation, "tags": value.tags}
            for value in values
        ],
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


def insert_lexeme_search_index(connection: sqlite3.Connection, words: Iterable[str]) -> int:
    """Insert normalized boundary n-grams for existing lexical words."""

    if not _has_table(connection, "lexeme_ngrams"):
        return 0
    rows = {(gram, normalize_word(word)) for word in words for gram in word_ngrams(word)}
    connection.executemany(
        "INSERT OR IGNORE INTO lexeme_ngrams(gram, word) VALUES (?, ?)",
        rows,
    )
    return len(rows)


def _search_field_values(sense: Sense) -> dict[str, tuple[str, ...]]:
    def related(values: tuple[str | RelatedTerm, ...]) -> tuple[str, ...]:
        return tuple(value if isinstance(value, str) else value.word for value in values)

    return {
        "glosses": sense.glosses,
        "topics": sense.topics,
        "tags": sense.tags,
        "examples": tuple(example.text for example in sense.examples),
        "synonyms": related(sense.synonyms),
        "antonyms": related(sense.antonyms),
    }


def insert_sense_search_terms(connection: sqlite3.Connection, sense_id: int, sense: Sense) -> int:
    """Insert counted normalized terms for the searchable sense fields."""

    if not _has_table(connection, "sense_search_terms"):
        return 0
    rows: list[tuple[str, int, str, int]] = []
    for field_name, values in _search_field_values(sense).items():
        counts = Counter(token for value in values for token in search_tokens(value))
        rows.extend((term, sense_id, field_name, count) for term, count in counts.items())
    connection.executemany(
        "INSERT OR REPLACE INTO sense_search_terms(term, sense_id, field, term_count) "
        "VALUES (?, ?, ?, ?)",
        rows,
    )
    return len(rows)


def insert_dictionary_entries(
    connection: sqlite3.Connection,
    entries: Iterable[DictionaryEntry],
    *,
    language: str = "en",
    identity_registry: SenseIdentityRegistry | None = None,
) -> tuple[int, int, set[str]]:
    entry_count = 0
    sense_count = 0
    words: set[str] = set()
    registry = identity_registry or SenseIdentityRegistry()
    rich = _has_table(connection, "entries")
    sense_topics = _has_table(connection, "sense_topics")
    search_terms = _has_table(connection, "sense_search_terms")
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
            "word, display_word, pos, entry_index, etymology_number, etymology, "
            "forms, pronunciations) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                word,
                display_word,
                entry.pos,
                entry_index,
                entry.etymology_number or "",
                entry.etymology or "",
                _json_forms(entry.forms),
                _json_pronunciations(entry.pronunciations),
            ),
        )
        assert cursor.lastrowid is not None
        entry_id = cursor.lastrowid
        for sense_index, sense in enumerate(entry.senses):
            base_anchor = sense_identity_anchor(language, entry, sense)
            duplicate_index = registry.counts.get(base_anchor, 0)
            registry.counts[base_anchor] = duplicate_index + 1
            anchor = sense_identity_anchor(language, entry, sense, duplicate_index)
            sense_id = stable_sense_int(anchor)
            prior_anchor = registry.ids.get(sense_id)
            if prior_anchor is not None and prior_anchor != anchor:
                raise SenseIdentityCollision(
                    f"deterministic sense ID collision for {sense_id}: "
                    f"{prior_anchor!r} != {anchor!r}"
                )
            if prior_anchor is not None:
                raise SenseIdentityCollision(f"duplicate deterministic sense ID {sense_id}")
            if connection.execute("SELECT 1 FROM senses WHERE id=?", (sense_id,)).fetchone():
                raise SenseIdentityCollision(f"deterministic sense ID already exists: {sense_id}")
            registry.ids[sense_id] = anchor
            sense_cursor = connection.execute(
                "INSERT INTO senses("
                "id, entry_id, sense_index, glosses, topics, tags, examples, synonyms, "
                "antonyms, source_ids) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    sense_id,
                    entry_id,
                    sense_index,
                    json_tuple(sense.glosses),
                    json_tuple(sense.topics),
                    json_tuple(sense.tags),
                    _json_examples(sense.examples),
                    _json_related(sense.synonyms),
                    _json_related(sense.antonyms),
                    _json_source_ids(sense.source_ids),
                ),
            )
            assert sense_cursor.rowcount == 1
            if sense_topics:
                for topic in sense.topics:
                    connection.execute(
                        "INSERT INTO sense_topics(topic, sense_id) VALUES (?, ?)",
                        (topic, sense_id),
                    )
            if search_terms:
                insert_sense_search_terms(connection, sense_id, sense)
    return entry_count, sense_count, words


def insert_headword_relations(
    connection: sqlite3.Connection, relations: Iterable[HeadwordRelation]
) -> int:
    if not _has_table(connection, "headword_relations"):
        return 0
    merged: dict[tuple[str, str, str], tuple[str, ...]] = {}
    for relation in relations:
        key = (
            normalize_word(relation.source),
            normalize_word(relation.target),
            relation.relation,
        )
        merged[key] = tuple(dict.fromkeys(merged.get(key, ()) + relation.tags))
    inserted = 0
    for (source, target, relation_name), tags in merged.items():
        encoded_tags = json_tuple(tags)
        existing = connection.execute(
            "SELECT tags FROM headword_relations "
            "WHERE source_word=? AND target_word=? AND relation=?",
            (source, target, relation_name),
        ).fetchone()
        if existing is None:
            connection.execute(
                "INSERT INTO headword_relations(source_word, target_word, relation, tags) "
                "VALUES (?, ?, ?, ?)",
                (source, target, relation_name, encoded_tags),
            )
            inserted += 1
            continue
        existing_tags = json.loads(str(existing[0]))
        combined = tuple(
            dict.fromkeys(tuple(item for item in existing_tags if isinstance(item, str)) + tags)
        )
        if json_tuple(combined) != str(existing[0]):
            connection.execute(
                "UPDATE headword_relations SET tags=? "
                "WHERE source_word=? AND target_word=? AND relation=?",
                (json_tuple(combined), source, target, relation_name),
            )
    return inserted


def create_schema(
    connection: sqlite3.Connection,
    capabilities: Iterable[str] = ("lexical", "semantic", "dictionary", "search"),
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
    if "search" in selected:
        connection.executescript(
            """
            CREATE TABLE lexeme_ngrams (
                gram TEXT NOT NULL,
                word TEXT NOT NULL,
                PRIMARY KEY (gram, word),
                FOREIGN KEY(word) REFERENCES lexemes(word)
            ) WITHOUT ROWID;
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
            ) WITHOUT ROWID;
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
                etymology_number TEXT NOT NULL DEFAULT '',
                etymology TEXT NOT NULL DEFAULT '',
                forms TEXT NOT NULL DEFAULT '[]',
                pronunciations TEXT NOT NULL DEFAULT '[]'
            );
            CREATE INDEX entries_word_idx ON entries(word);
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
                source_ids TEXT NOT NULL DEFAULT '[]',
                FOREIGN KEY(entry_id) REFERENCES entries(id) ON DELETE CASCADE
            );
            CREATE INDEX senses_entry_idx ON senses(entry_id);
            CREATE TABLE sense_topics (
                topic TEXT NOT NULL,
                sense_id INTEGER NOT NULL,
                PRIMARY KEY(topic, sense_id),
                FOREIGN KEY(sense_id) REFERENCES senses(id) ON DELETE CASCADE
            ) WITHOUT ROWID;
            """
        )
        if "search" in selected:
            connection.executescript(
                """
                CREATE TABLE sense_search_terms (
                    term TEXT NOT NULL,
                    sense_id INTEGER NOT NULL,
                    field TEXT NOT NULL,
                    term_count INTEGER NOT NULL,
                    PRIMARY KEY (term, sense_id, field),
                    FOREIGN KEY(sense_id) REFERENCES senses(id) ON DELETE CASCADE
                ) WITHOUT ROWID;
                """
            )
        connection.executescript(
            """
            CREATE TABLE headword_relations (
                source_word TEXT NOT NULL,
                target_word TEXT NOT NULL,
                relation TEXT NOT NULL,
                tags TEXT NOT NULL DEFAULT '[]',
                PRIMARY KEY (source_word, target_word, relation)
            ) WITHOUT ROWID;
            CREATE INDEX headword_relations_target_idx
                ON headword_relations(target_word, relation);
            """
        )


def finalize_artifact(connection: sqlite3.Connection) -> None:
    """Validate and compact an immutable schema 10 artifact."""
    artifact_metadata = metadata(connection)
    if artifact_metadata.get("schema_version") != SCHEMA_VERSION:
        raise SchemaContractError(
            f"artifact finalization requires schema {SCHEMA_VERSION}, "
            f"got {artifact_metadata.get('schema_version', 'unknown')}"
        )
    capabilities = canonical_capabilities(
        item for item in artifact_metadata.get("capabilities", "").split(",") if item
    )
    validate_artifact_structure(connection, capabilities)
    connection.execute(f"PRAGMA application_id = {SQLITE_APPLICATION_ID}")
    connection.execute(f"PRAGMA user_version = {SQLITE_USER_VERSION}")
    connection.commit()
    foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_keys:
        raise sqlite3.DatabaseError(f"foreign key check failed: {foreign_keys[0]!r}")
    quick_check = connection.execute("PRAGMA quick_check").fetchone()
    if quick_check != ("ok",):
        raise sqlite3.DatabaseError(f"quick_check failed: {quick_check!r}")
    connection.execute("ANALYZE")
    connection.commit()
    connection.execute("VACUUM")
    quick_check = connection.execute("PRAGMA quick_check").fetchone()
    if quick_check != ("ok",):
        raise sqlite3.DatabaseError(f"quick_check failed after VACUUM: {quick_check!r}")
    connection.commit()


def metadata(connection: sqlite3.Connection) -> dict[str, str]:
    return {
        str(row[0]): str(row[1]) for row in connection.execute("SELECT key, value FROM metadata")
    }


def set_metadata(connection: sqlite3.Connection, values: Mapping[str, str]) -> None:
    connection.executemany(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)", values.items()
    )


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
