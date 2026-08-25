from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

SCHEMA_VERSION = "10"
SQLITE_APPLICATION_ID = 0x4C584831
SQLITE_USER_VERSION = 10
CAPABILITY_ORDER = ("lexical", "semantic", "dictionary", "search")
CAPABILITIES = frozenset(CAPABILITY_ORDER)


class SchemaContractError(ValueError):
    """A SQLite artifact does not satisfy the schema-10 structural contract."""


@dataclass(frozen=True, slots=True)
class ColumnContract:
    name: str
    type: str
    notnull: int
    default: str | None


@dataclass(frozen=True, slots=True)
class ForeignKeyContract:
    column: str
    table: str
    target_column: str
    on_delete: str


@dataclass(frozen=True, slots=True)
class IndexContract:
    name: str
    columns: tuple[str, ...]
    unique: bool = False


@dataclass(frozen=True, slots=True)
class TableContract:
    columns: tuple[ColumnContract, ...]
    primary_key: tuple[str, ...]
    foreign_keys: tuple[ForeignKeyContract, ...] = ()
    without_rowid: bool = False
    indexes: tuple[IndexContract, ...] = ()


@dataclass(frozen=True, slots=True)
class SchemaContract:
    tables: tuple[str, ...]


_METADATA = TableContract(
    columns=(
        ColumnContract("key", "TEXT", 0, None),
        ColumnContract("value", "TEXT", 1, None),
    ),
    primary_key=("key",),
)
_LEXEMES = TableContract(
    columns=(
        ColumnContract("word", "TEXT", 0, None),
        ColumnContract("entry_count", "INTEGER", 1, None),
        ColumnContract("has_lowercase", "INTEGER", 1, None),
        ColumnContract("has_titlecase", "INTEGER", 1, None),
        ColumnContract("has_uppercase", "INTEGER", 1, None),
        ColumnContract("corpus_count", "INTEGER", 0, None),
        ColumnContract("corpus_rank", "INTEGER", 0, None),
    ),
    primary_key=("word",),
    indexes=(IndexContract("lexemes_corpus_rank_idx", ("corpus_rank",)),),
)
_LEXEME_NGRAMS = TableContract(
    columns=(ColumnContract("gram", "TEXT", 1, None), ColumnContract("word", "TEXT", 1, None)),
    primary_key=("gram", "word"),
    foreign_keys=(ForeignKeyContract("word", "lexemes", "word", "NO ACTION"),),
    without_rowid=True,
)
_LEXEME_DOMAINS = TableContract(
    columns=(
        ColumnContract("word", "TEXT", 1, None),
        ColumnContract("domain", "TEXT", 1, None),
        ColumnContract("weight", "REAL", 1, None),
        ColumnContract("source_topics", "TEXT", 1, None),
    ),
    primary_key=("word", "domain"),
    foreign_keys=(ForeignKeyContract("word", "lexemes", "word", "NO ACTION"),),
    without_rowid=True,
    indexes=(IndexContract("lexeme_domains_domain_idx", ("domain",)),),
)
_ENTRIES = TableContract(
    columns=(
        ColumnContract("id", "INTEGER", 0, None),
        ColumnContract("word", "TEXT", 1, None),
        ColumnContract("display_word", "TEXT", 1, None),
        ColumnContract("pos", "TEXT", 1, None),
        ColumnContract("entry_index", "INTEGER", 1, None),
        ColumnContract("etymology_number", "TEXT", 1, "''"),
        ColumnContract("etymology", "TEXT", 1, "''"),
        ColumnContract("forms", "TEXT", 1, "'[]'"),
        ColumnContract("pronunciations", "TEXT", 1, "'[]'"),
    ),
    primary_key=("id",),
    indexes=(IndexContract("entries_word_idx", ("word",)),),
)
_SENSES = TableContract(
    columns=(
        ColumnContract("id", "INTEGER", 0, None),
        ColumnContract("entry_id", "INTEGER", 1, None),
        ColumnContract("sense_index", "INTEGER", 1, None),
        ColumnContract("glosses", "TEXT", 1, None),
        ColumnContract("topics", "TEXT", 1, None),
        ColumnContract("tags", "TEXT", 1, None),
        ColumnContract("examples", "TEXT", 1, None),
        ColumnContract("synonyms", "TEXT", 1, None),
        ColumnContract("antonyms", "TEXT", 1, None),
        ColumnContract("source_ids", "TEXT", 1, "'[]'"),
    ),
    primary_key=("id",),
    foreign_keys=(ForeignKeyContract("entry_id", "entries", "id", "CASCADE"),),
    indexes=(IndexContract("senses_entry_idx", ("entry_id",)),),
)
_SENSE_TOPICS = TableContract(
    columns=(
        ColumnContract("topic", "TEXT", 1, None),
        ColumnContract("sense_id", "INTEGER", 1, None),
    ),
    primary_key=("topic", "sense_id"),
    foreign_keys=(ForeignKeyContract("sense_id", "senses", "id", "CASCADE"),),
    without_rowid=True,
)
_HEADWORD_RELATIONS = TableContract(
    columns=(
        ColumnContract("source_word", "TEXT", 1, None),
        ColumnContract("target_word", "TEXT", 1, None),
        ColumnContract("relation", "TEXT", 1, None),
        ColumnContract("tags", "TEXT", 1, "'[]'"),
    ),
    primary_key=("source_word", "target_word", "relation"),
    without_rowid=True,
    indexes=(IndexContract("headword_relations_target_idx", ("target_word", "relation")),),
)
_SENSE_SEARCH_TERMS = TableContract(
    columns=(
        ColumnContract("term", "TEXT", 1, None),
        ColumnContract("sense_id", "INTEGER", 1, None),
        ColumnContract("field", "TEXT", 1, None),
        ColumnContract("term_count", "INTEGER", 1, None),
    ),
    primary_key=("term", "sense_id", "field"),
    foreign_keys=(ForeignKeyContract("sense_id", "senses", "id", "CASCADE"),),
    without_rowid=True,
)

TABLE_CONTRACTS: Mapping[str, TableContract] = {
    "metadata": _METADATA,
    "lexemes": _LEXEMES,
    "lexeme_ngrams": _LEXEME_NGRAMS,
    "lexeme_domains": _LEXEME_DOMAINS,
    "entries": _ENTRIES,
    "senses": _SENSES,
    "sense_topics": _SENSE_TOPICS,
    "headword_relations": _HEADWORD_RELATIONS,
    "sense_search_terms": _SENSE_SEARCH_TERMS,
}

_CAPABILITY_TABLES: Mapping[str, tuple[str, ...]] = {
    "lexical": ("lexemes",),
    "semantic": ("lexeme_domains",),
    "dictionary": ("entries", "senses", "sense_topics", "headword_relations"),
    "search": ("lexeme_ngrams",),
}

SCHEMA_CONTRACT: Mapping[str, SchemaContract] = {
    "lexical": SchemaContract(("metadata", "lexemes")),
    "runtime": SchemaContract(("metadata", "lexemes", "lexeme_domains")),
    "dictionary": SchemaContract(
        (
            "metadata",
            "lexemes",
            "lexeme_domains",
            "entries",
            "senses",
            "sense_topics",
            "headword_relations",
        )
    ),
    "rich": SchemaContract(
        (
            "metadata",
            "lexemes",
            "lexeme_domains",
            "entries",
            "senses",
            "sense_topics",
            "headword_relations",
            "lexeme_ngrams",
            "sense_search_terms",
        )
    ),
}

PERSISTED_FORMAT_VERSIONS: Mapping[str, str] = {
    "dictionary_source_contract": "1",
    "search_index_version": "1",
    "sense_id_format": "lh1",
}


def canonical_capabilities(capabilities: Iterable[str]) -> tuple[str, ...]:
    selected = tuple(dict.fromkeys(capabilities))
    unknown = sorted(set(selected) - CAPABILITIES)
    if unknown:
        raise SchemaContractError(f"unknown capability {unknown[0]!r}")
    if not selected or "lexical" not in selected:
        raise SchemaContractError("schema artifacts require the 'lexical' capability")
    for dependent in ("semantic", "dictionary", "search"):
        if dependent in selected and "lexical" not in selected:
            raise SchemaContractError(f"capability {dependent!r} requires capability 'lexical'")
    return tuple(capability for capability in CAPABILITY_ORDER if capability in selected)


def schema_contract(capabilities: Iterable[str]) -> SchemaContract:
    selected = canonical_capabilities(capabilities)
    tables = ["metadata", "lexemes"]
    for capability in selected:
        for table in _CAPABILITY_TABLES.get(capability, ()):
            if table not in tables:
                tables.append(table)
    return SchemaContract(tuple(tables))


def _table_sql(connection: sqlite3.Connection, table: str) -> str:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return str(row[0]) if row is not None and row[0] is not None else ""


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _inspect_table(connection: sqlite3.Connection, table: str) -> TableContract:
    columns = tuple(
        ColumnContract(str(row[1]), str(row[2]), int(row[3]), row[4])
        for row in connection.execute(f"PRAGMA table_info({_quote(table)})")
    )
    primary_key = tuple(
        str(row[1])
        for row in sorted(
            (
                row
                for row in connection.execute(f"PRAGMA table_info({_quote(table)})")
                if int(row[5])
            ),
            key=lambda row: int(row[5]),
        )
    )
    foreign_keys = tuple(
        ForeignKeyContract(str(row[3]), str(row[2]), str(row[4]), str(row[6]).upper())
        for row in connection.execute(f"PRAGMA foreign_key_list({_quote(table)})")
    )
    indexes: list[IndexContract] = []
    for row in connection.execute(f"PRAGMA index_list({_quote(table)})"):
        name = str(row[1])
        if str(row[3]) == "pk" or name.startswith("sqlite_autoindex"):
            continue
        index_columns = tuple(
            str(index_row[2])
            for index_row in sorted(
                connection.execute(f"PRAGMA index_info({_quote(name)})"),
                key=lambda index_row: int(index_row[0]),
            )
        )
        indexes.append(IndexContract(name, index_columns, bool(row[2])))
    return TableContract(
        columns=columns,
        primary_key=primary_key,
        foreign_keys=foreign_keys,
        without_rowid="WITHOUT ROWID" in _table_sql(connection, table).upper(),
        indexes=tuple(sorted(indexes, key=lambda index: index.name)),
    )


def inspect_schema(connection: sqlite3.Connection) -> Mapping[str, TableContract]:
    tables = tuple(
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    )
    return {table: _inspect_table(connection, table) for table in tables}


def _mismatch(table: str, field: str, expected: object, actual: object) -> SchemaContractError:
    return SchemaContractError(
        f"schema {SCHEMA_VERSION} contract mismatch for {table}.{field}: "
        f"expected {expected!r}, got {actual!r}; decide compatibility and bump SCHEMA_VERSION "
        "if this is an incompatible artifact change"
    )


def validate_artifact_structure(
    connection: sqlite3.Connection, capabilities: Iterable[str]
) -> None:
    """Validate required schema-10 objects for the selected capabilities."""
    selected = canonical_capabilities(capabilities)
    expected_schema = schema_contract(selected)
    actual_schema = inspect_schema(connection)
    missing = tuple(table for table in expected_schema.tables if table not in actual_schema)
    if missing:
        raise _mismatch("artifact", "tables", expected_schema.tables, tuple(actual_schema))
    for table in expected_schema.tables:
        expected = TABLE_CONTRACTS[table]
        actual = actual_schema[table]
        if actual.columns != expected.columns:
            raise _mismatch(table, "columns", expected.columns, actual.columns)
        if actual.primary_key != expected.primary_key:
            raise _mismatch(table, "primary_key", expected.primary_key, actual.primary_key)
        if actual.foreign_keys != expected.foreign_keys:
            raise _mismatch(table, "foreign_keys", expected.foreign_keys, actual.foreign_keys)
        if actual.without_rowid != expected.without_rowid:
            raise _mismatch(table, "without_rowid", expected.without_rowid, actual.without_rowid)
        actual_indexes = {index.name: index for index in actual.indexes}
        for index in expected.indexes:
            if actual_indexes.get(index.name) != index:
                raise _mismatch(table, f"index {index.name}", index, actual_indexes.get(index.name))
