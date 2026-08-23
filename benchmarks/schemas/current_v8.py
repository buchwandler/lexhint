"""Historical snapshot of Lexhint schema 8 for benchmark comparisons."""

from __future__ import annotations

import json
import sqlite3
import time
from collections import defaultdict
from collections.abc import Iterable

from lexhint.search import FIELD_WEIGHTS, edit_distance, search_tokens, word_ngrams

from ..generate import DOMAINS, SyntheticGenerator
from ..model import SyntheticDataset, SyntheticSense
from ..schema_api import BuildMetrics, SchemaAdapter, capability_set

DDL_BASE = """
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
DDL_SEARCH = """
CREATE TABLE lexeme_ngrams (
    gram TEXT NOT NULL,
    word TEXT NOT NULL,
    PRIMARY KEY (gram, word),
    FOREIGN KEY(word) REFERENCES lexemes(word)
);
CREATE INDEX lexeme_ngrams_word_idx ON lexeme_ngrams(word);
"""
DDL_SEMANTIC = """
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
DDL_DICTIONARY = """
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
DDL_SEARCH_TERMS = """
CREATE TABLE sense_search_terms (
    term TEXT NOT NULL,
    sense_id INTEGER NOT NULL,
    field TEXT NOT NULL,
    term_count INTEGER NOT NULL,
    PRIMARY KEY (term, sense_id, field),
    FOREIGN KEY(sense_id) REFERENCES senses(id) ON DELETE CASCADE
);
CREATE INDEX sense_search_terms_sense_idx ON sense_search_terms(sense_id);
"""


def _row_dict(row: sqlite3.Row | None) -> dict[str, object] | None:
    return dict(row) if row is not None else None


def _insert_batches(
    connection: sqlite3.Connection,
    sql: str,
    rows: Iterable[tuple[object, ...]],
    batch_size: int,
) -> int:
    batch: list[tuple[object, ...]] = []
    total = 0
    for row in rows:
        batch.append(row)
        if len(batch) >= batch_size:
            connection.executemany(sql, batch)
            total += len(batch)
            batch.clear()
    if batch:
        connection.executemany(sql, batch)
        total += len(batch)
    return total


def _json_values(value: str) -> tuple[str, ...]:
    loaded = json.loads(value)
    return (
        tuple(item for item in loaded if isinstance(item, str)) if isinstance(loaded, list) else ()
    )


def _search_rows(sense: SyntheticSense) -> list[tuple[str, int, str, int]]:
    rows: list[tuple[str, int, str, int]] = []
    for field, values in sense.search_fields:
        counts: defaultdict[str, int] = defaultdict(int)
        for value in values:
            for term in search_tokens(value):
                counts[term] += 1
        rows.extend((term, sense.sense_id, field, count) for term, count in counts.items())
    return rows


class CurrentV8Adapter(SchemaAdapter):
    name = "current-v8"
    source_schema_version = "8"
    description = "Historical schema 8 equivalent with Lexhint search queries."
    supported_workloads = frozenset({"exact", "completion", "suggest", "dictionary", "definition"})

    def __init__(self, *, capabilities: tuple[str, ...] | None = None):
        self.capabilities = capability_set(capabilities)

    def create(self, connection: sqlite3.Connection) -> None:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(DDL_BASE)
        if "search" in self.capabilities:
            connection.executescript(DDL_SEARCH)
        if "semantic" in self.capabilities:
            connection.executescript(DDL_SEMANTIC)
        if "dictionary" in self.capabilities:
            connection.executescript(DDL_DICTIONARY)
            if "search" in self.capabilities:
                connection.executescript(DDL_SEARCH_TERMS)

    def populate(
        self,
        connection: sqlite3.Connection,
        dataset: SyntheticDataset,
        *,
        batch_size: int,
    ) -> BuildMetrics:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        generator = SyntheticGenerator(dataset.profile)
        metrics = BuildMetrics(counts={})
        connection.execute("BEGIN")
        start = time.perf_counter_ns()
        lexeme_rows = (
            (
                row.word,
                row.entry_count,
                row.has_lowercase,
                row.has_titlecase,
                row.has_uppercase,
                row.corpus_count,
                row.corpus_rank,
            )
            for row in generator.iter_lexemes()
        )
        metrics.counts["lexemes"] = _insert_batches(
            connection, "INSERT INTO lexemes VALUES (?, ?, ?, ?, ?, ?, ?)", lexeme_rows, batch_size
        )
        metrics.phases["lexemes"] = self._phase(start, metrics.counts["lexemes"])
        if "search" in self.capabilities:
            start = time.perf_counter_ns()
            ngram_rows = (
                (gram, row.word)
                for row in generator.iter_lexemes()
                for gram in word_ngrams(row.word)
            )
            metrics.counts["lexeme_ngrams"] = _insert_batches(
                connection,
                "INSERT INTO lexeme_ngrams(gram, word) VALUES (?, ?)",
                ngram_rows,
                batch_size,
            )
            metrics.phases["lexeme_ngrams"] = self._phase(start, metrics.counts["lexeme_ngrams"])
        if "semantic" in self.capabilities:
            start = time.perf_counter_ns()
            metrics.counts["semantic_rows"] = _insert_batches(
                connection,
                "INSERT INTO lexeme_domains(word, domain, weight, source_topics) "
                "VALUES (?, ?, ?, ?)",
                self._semantic_rows(generator),
                batch_size,
            )
            metrics.phases["semantic"] = self._phase(start, metrics.counts["semantic_rows"])
        if "dictionary" in self.capabilities:
            start = time.perf_counter_ns()
            entry_rows = (
                (
                    e.entry_id,
                    e.word,
                    e.display_word,
                    e.pos,
                    e.entry_index,
                    e.etymology,
                    e.forms_json,
                    e.pronunciations_json,
                )
                for e in generator.iter_entries()
            )
            metrics.counts["entries"] = _insert_batches(
                connection,
                "INSERT INTO entries VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                entry_rows,
                batch_size,
            )
            metrics.phases["entries"] = self._phase(start, metrics.counts["entries"])
            start = time.perf_counter_ns()
            sense_rows = (
                (
                    s.sense_id,
                    s.entry_id,
                    s.sense_index,
                    s.glosses_json,
                    s.topics_json,
                    s.tags_json,
                    s.examples_json,
                    s.synonyms_json,
                    s.antonyms_json,
                )
                for s in generator.iter_senses()
            )
            metrics.counts["senses"] = _insert_batches(
                connection,
                "INSERT INTO senses VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                sense_rows,
                batch_size,
            )
            metrics.phases["senses"] = self._phase(start, metrics.counts["senses"])
            topic_rows = (
                (s.entry_id, s.sense_id, topic)
                for s in generator.iter_senses()
                for topic in _json_values(s.topics_json)
            )
            metrics.counts["sense_topics"] = _insert_batches(
                connection,
                "INSERT INTO sense_topics(entry_id, sense_id, topic) VALUES (?, ?, ?)",
                topic_rows,
                batch_size,
            )
            if "search" in self.capabilities:
                start = time.perf_counter_ns()
                terms = (row for sense in generator.iter_senses() for row in _search_rows(sense))
                metrics.counts["sense_search_terms"] = _insert_batches(
                    connection,
                    "INSERT INTO sense_search_terms(term, sense_id, field, term_count) "
                    "VALUES (?, ?, ?, ?)",
                    terms,
                    batch_size,
                )
                metrics.phases["sense_search_terms"] = self._phase(
                    start, metrics.counts["sense_search_terms"]
                )
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES (?, ?)",
            ("schema_version", self.source_schema_version),
        )
        connection.execute(
            "INSERT INTO metadata(key, value) VALUES (?, ?)",
            ("benchmark_profile", dataset.profile.name),
        )
        return metrics

    @staticmethod
    def _phase(start: int, rows: int) -> dict[str, float | int]:
        seconds = max((time.perf_counter_ns() - start) / 1_000_000_000, 1e-9)
        return {"seconds": seconds, "rows": rows, "rows_per_second": rows / seconds}

    @staticmethod
    def _semantic_rows(generator: SyntheticGenerator) -> Iterable[tuple[object, ...]]:
        for index, lexeme in enumerate(generator.iter_lexemes()):
            rng = generator._rng(index, 29)
            if rng.random() >= generator.profile.semantic_coverage:
                continue
            mean = generator.profile.domains_per_semantic_lexeme_mean
            count = int(mean) + int(rng.random() < mean - int(mean))
            for offset in range(max(1, count)):
                domain = DOMAINS[(index + offset) % len(DOMAINS)]
                yield (
                    lexeme.word,
                    domain,
                    1.0 / (offset + 1),
                    json.dumps([domain], separators=(",", ":")),
                )

    def finalize(self, connection: sqlite3.Connection) -> None:
        connection.execute("ANALYZE")
        connection.commit()

    def exact_lookup(self, connection: sqlite3.Connection, word: str) -> dict[str, object] | None:
        return _row_dict(
            connection.execute(
                "SELECT corpus_count, corpus_rank, has_lowercase, has_titlecase, has_uppercase "
                "FROM lexemes WHERE word=?",
                (word.casefold(),),
            ).fetchone()
        )

    def complete(self, connection: sqlite3.Connection, prefix: str, limit: int) -> list[str]:
        prefix = prefix.casefold()
        return [
            row[0]
            for row in connection.execute(
                "SELECT word FROM lexemes WHERE word >= ? AND word < ? "
                "ORDER BY corpus_rank IS NULL, corpus_rank, word LIMIT ?",
                (prefix, prefix + "\uffff", limit),
            )
        ]

    def suggest(self, connection: sqlite3.Connection, query: str, limit: int) -> dict[str, object]:
        grams = word_ngrams(query)
        if not grams or "search" not in self.capabilities:
            return {
                "candidates": [],
                "candidate_rows": 0,
                "candidate_words": 0,
                "surviving_words": 0,
            }
        placeholders = ",".join("?" for _ in grams)
        rows = connection.execute(
            f"SELECT n.word, l.corpus_rank, COUNT(*) AS overlap FROM lexeme_ngrams n "
            f"JOIN lexemes l ON l.word=n.word WHERE n.gram IN ({placeholders}) "
            "GROUP BY n.word ORDER BY overlap DESC, n.word LIMIT ?",
            (*grams, max(limit * 8, limit)),
        ).fetchall()
        ranked: list[tuple[int, int | None, str]] = []
        for word, rank, _ in rows:
            distance = edit_distance(query, word, max_distance=2)
            if distance <= 2:
                ranked.append((distance, rank, word))
        ranked.sort(key=lambda item: (item[0], item[1] is None, item[1] or 0, item[2]))
        return {
            "candidates": [word for _, _, word in ranked[:limit]],
            "candidate_rows": len(rows),
            "candidate_words": len(rows),
            "surviving_words": len(ranked),
            "gram_count": len(grams),
        }

    def dictionary_lookup(
        self, connection: sqlite3.Connection, word: str
    ) -> list[dict[str, object]]:
        if "dictionary" not in self.capabilities:
            return []
        entries = []
        for entry in connection.execute(
            "SELECT * FROM entries WHERE word=? ORDER BY entry_index", (word.casefold(),)
        ):
            result = dict(entry)
            result["senses"] = [
                dict(sense)
                for sense in connection.execute(
                    "SELECT * FROM senses WHERE entry_id=? ORDER BY sense_index", (entry["id"],)
                )
            ]
            entries.append(result)
        return entries

    def definition_search(
        self,
        connection: sqlite3.Connection,
        terms: tuple[str, ...],
        *,
        match: str = "all",
        limit: int = 20,
    ) -> list[dict[str, object]]:
        if "search" not in self.capabilities or "dictionary" not in self.capabilities:
            return []
        normalized = tuple(dict.fromkeys(term.casefold() for term in terms if term))
        if not normalized or match not in {"all", "any"}:
            return []
        placeholders = ",".join("?" for _ in normalized)
        rows = connection.execute(
            f"SELECT term, sense_id, field, term_count FROM sense_search_terms "
            f"WHERE term IN ({placeholders})",
            normalized,
        ).fetchall()
        grouped: dict[int, dict[str, object]] = {}
        for row in rows:
            item = grouped.setdefault(
                row["sense_id"], {"terms": set(), "fields": set(), "score": 0.0, "index_rows": 0}
            )
            item["terms"].add(row["term"])
            item["fields"].add(row["field"])
            item["score"] += FIELD_WEIGHTS.get(row["field"], 1.0) * min(int(row["term_count"]), 3)
            item["index_rows"] += 1
        if match == "all":
            grouped = {
                key: value
                for key, value in grouped.items()
                if len(value["terms"]) == len(normalized)
            }
        results: list[dict[str, object]] = []
        for sense_id, item in grouped.items():
            sense = connection.execute(
                "SELECT s.*, e.word, e.pos FROM senses s JOIN entries e "
                "ON e.id=s.entry_id WHERE s.id=?",
                (sense_id,),
            ).fetchone()
            if sense is None:
                continue
            results.append(
                {
                    "word": sense["word"],
                    "pos": sense["pos"],
                    "sense_index": sense["sense_index"],
                    "glosses": _json_values(sense["glosses"]),
                    "score": item["score"],
                    "matched_terms": tuple(sorted(item["terms"])),
                    "matched_fields": tuple(sorted(item["fields"])),
                    "index_rows": item["index_rows"],
                }
            )
        results.sort(
            key=lambda value: (-float(value["score"]), value["word"], int(value["sense_index"]))
        )
        return results[:limit]
