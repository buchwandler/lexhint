import sqlite3
from contextlib import closing

import pytest

from lexhint.frequency import enrich_frequency, iter_frequency_rows


def test_frequency_rows_normalize_and_keep_first_duplicate() -> None:
    rows = tuple(iter_frequency_rows(["The 1000\n", "Compiler 100\n", "compiler 50\n"]))
    assert rows[0].word == "the"
    assert rows[1].word == "compiler"
    assert rows[1].rank == 2
    assert rows[1].count == 100


def test_frequency_parser_rejects_invalid_or_negative_counts() -> None:
    with pytest.raises(ValueError):
        tuple(iter_frequency_rows(["broken\n"]))
    with pytest.raises(ValueError):
        tuple(iter_frequency_rows(["word -1\n"]))


def test_enrichment_does_not_create_corpus_only_lexemes() -> None:
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.execute(
            "CREATE TABLE lexemes ("
            "word TEXT PRIMARY KEY, corpus_count INTEGER, corpus_rank INTEGER"
            ")"
        )
        connection.execute("INSERT INTO lexemes VALUES ('known', NULL, NULL)")
        stats = enrich_frequency(
            connection,
            iter_frequency_rows(["known 10\n", "corpusonly 20\n"]),
        )
        assert stats.rows == 2
        assert stats.matched_lexemes == 1
        assert connection.execute("SELECT * FROM lexemes").fetchall() == [("known", 10, 1)]
