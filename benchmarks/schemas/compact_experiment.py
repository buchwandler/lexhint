"""Schema 8 search tables using WITHOUT ROWID."""

from __future__ import annotations

from .current_v8 import CurrentV8Adapter


class WithoutRowidSearchAdapter(CurrentV8Adapter):
    name = "current-v8-without-rowid-search"
    description = "Schema 8 equivalent with WITHOUT ROWID compound search tables."

    def create(self, connection):
        super().create(connection)
        # Rebuild only the two compound-key tables. This keeps the rest of the
        # snapshot and all workload semantics identical while changing one variable.
        for table in ("sense_search_terms", "lexeme_ngrams"):
            row = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            if row is None:
                continue
            connection.execute(f"ALTER TABLE {table} RENAME TO {table}_rowid")
            sql = row[0].replace("\n", " ").rstrip(";") + " WITHOUT ROWID"
            connection.execute(sql.replace(table, table, 1))
            connection.execute(f"INSERT INTO {table} SELECT * FROM {table}_rowid")
            connection.execute(f"DROP TABLE {table}_rowid")
            if table == "lexeme_ngrams":
                connection.execute("CREATE INDEX lexeme_ngrams_word_idx ON lexeme_ngrams(word)")
            else:
                connection.execute(
                    "CREATE INDEX sense_search_terms_sense_idx ON sense_search_terms(sense_id)"
                )
        connection.commit()
