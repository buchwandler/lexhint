"""Schema 8 benchmark variant with a normalized headword relation table."""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterable

from ..model import SyntheticDataset
from ..schema_api import BuildMetrics
from .current_v8 import CurrentV8Adapter, _insert_batches

DDL_RELATIONS = """
CREATE TABLE headword_relations (
    source_word TEXT NOT NULL,
    target_word TEXT NOT NULL,
    relation TEXT NOT NULL,
    tags TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (source_word, target_word, relation)
);
CREATE INDEX headword_relations_target_idx
    ON headword_relations(target_word, relation);
CREATE INDEX headword_relations_relation_idx
    ON headword_relations(relation, source_word);
"""


class CurrentV8RelationsAdapter(CurrentV8Adapter):
    name = "current-v8-relations"
    description = "Schema 8 benchmark equivalent plus measured headword relations."
    supported_workloads = CurrentV8Adapter.supported_workloads | frozenset({"relations"})

    def create(self, connection: sqlite3.Connection) -> None:
        super().create(connection)
        if "dictionary" in self.capabilities:
            connection.executescript(DDL_RELATIONS)

    def populate(
        self,
        connection: sqlite3.Connection,
        dataset: SyntheticDataset,
        *,
        batch_size: int,
    ) -> BuildMetrics:
        metrics = super().populate(connection, dataset, batch_size=batch_size)
        if "dictionary" not in self.capabilities:
            return metrics
        relation_start = time.perf_counter_ns()
        rows = (
            (relation.source, relation.target, relation.relation, relation.tags_json)
            for relation in dataset.iter_relations()
        )
        inserted = _insert_batches(
            connection,
            "INSERT INTO headword_relations(source_word, target_word, relation, tags) "
            "VALUES (?, ?, ?, ?)",
            rows,
            batch_size,
        )
        metrics.counts["relations"] = inserted
        metrics.phases["relations"] = self._phase(relation_start, inserted)
        return metrics

    @staticmethod
    def _relation_rows(rows: Iterable[sqlite3.Row]) -> list[dict[str, object]]:
        return [
            {
                "source_word": str(row["source_word"]),
                "target_word": str(row["target_word"]),
                "relation": str(row["relation"]),
                "tags": tuple(json.loads(str(row["tags"]))),
            }
            for row in rows
        ]

    def relation_lookup(
        self, connection: sqlite3.Connection, word: str, limit: int = 20
    ) -> list[dict[str, object]]:
        if "dictionary" not in self.capabilities:
            return []
        rows = connection.execute(
            "SELECT source_word, target_word, relation, tags FROM headword_relations "
            "WHERE source_word=? ORDER BY relation, target_word LIMIT ?",
            (word, limit),
        ).fetchall()
        return self._relation_rows(rows)

    def reverse_relation_lookup(
        self, connection: sqlite3.Connection, word: str, limit: int = 20
    ) -> list[dict[str, object]]:
        if "dictionary" not in self.capabilities:
            return []
        rows = connection.execute(
            "SELECT source_word, target_word, relation, tags FROM headword_relations "
            "WHERE target_word=? ORDER BY relation, source_word LIMIT ?",
            (word, limit),
        ).fetchall()
        return self._relation_rows(rows)

    def resolve_headword(
        self,
        connection: sqlite3.Connection,
        word: str,
        relations: tuple[str, ...] = ("redirect", "alternative", "form_of"),
        limit: int = 20,
    ) -> list[str]:
        if "dictionary" not in self.capabilities or not relations:
            return []
        placeholders = ",".join("?" for _ in relations)
        rows = connection.execute(
            "SELECT target_word FROM headword_relations "
            f"WHERE source_word=? AND relation IN ({placeholders}) "
            "ORDER BY relation, target_word LIMIT ?",
            (word, *relations, limit),
        ).fetchall()
        return [str(row[0]) for row in rows]
