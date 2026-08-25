"""Schema 10 benchmark candidate with compact compound-key tables."""

from __future__ import annotations

import sqlite3

from .current_v8_relations import CurrentV8RelationsAdapter


class Schema10CandidateAdapter(CurrentV8RelationsAdapter):
    name = "schema10-candidate"
    source_schema_version = "10"
    description = "Schema 10 candidate with WITHOUT ROWID and read-only index finalization."

    @staticmethod
    def _without_rowid(connection: sqlite3.Connection, table: str) -> None:
        row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        if row is None or not row[0]:
            return
        temporary = f"{table}_rowid"
        connection.execute(f"ALTER TABLE {table} RENAME TO {temporary}")
        sql = str(row[0]).rstrip().rstrip(";") + " WITHOUT ROWID"
        connection.execute(sql)
        connection.execute(f"INSERT INTO {table} SELECT * FROM {temporary}")
        connection.execute(f"DROP TABLE {temporary}")

    def create(self, connection: sqlite3.Connection) -> None:
        super().create(connection)
        for table in ("lexeme_ngrams", "sense_search_terms", "headword_relations"):
            self._without_rowid(connection, table)
        for index in (
            "entries_display_word_idx",
            "lexeme_ngrams_word_idx",
            "sense_topics_topic_idx",
            "sense_topics_entry_idx",
            "sense_search_terms_sense_idx",
            "headword_relations_relation_idx",
        ):
            connection.execute(f"DROP INDEX IF EXISTS {index}")
        connection.commit()
