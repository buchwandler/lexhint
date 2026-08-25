from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from lexhint import Lexicon, project_artifact
from lexhint.builder import build_dictionary

FIXTURE = Path(__file__).parent / "fixtures" / "kaikki-rich.jsonl"


def test_schema10_uses_compact_tables_and_finalizes_artifact(tmp_path: Path) -> None:
    database, _ = build_dictionary(
        "en", FIXTURE, output=tmp_path / "rich.sqlite3", profile="rich", no_frequency=True
    )
    connection = sqlite3.connect(database)
    try:
        assert connection.execute("PRAGMA quick_check").fetchone() == ("ok",)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA application_id").fetchone() == (0x4C584831,)
        assert connection.execute("PRAGMA user_version").fetchone() == (10,)
        sql = {
            row[0]: str(row[1] or "")
            for row in connection.execute(
                "SELECT name, sql FROM sqlite_master WHERE type IN ('table', 'index')"
            )
        }
        assert "WITHOUT ROWID" in sql["sense_topics"]
        assert "WITHOUT ROWID" in sql["sense_search_terms"]
        assert "WITHOUT ROWID" in sql["lexeme_ngrams"]
        assert "WITHOUT ROWID" in sql["headword_relations"]
        assert "entries_display_word_idx" not in sql
        assert "lexeme_ngrams_word_idx" not in sql
        assert "sense_search_terms_sense_idx" not in sql
        assert "headword_relations_relation_idx" not in sql
    finally:
        connection.close()


def test_dictionary_projection_preserves_option_b_topics(tmp_path: Path) -> None:
    source, _ = build_dictionary(
        "en", FIXTURE, output=tmp_path / "source.sqlite3", profile="rich", no_frequency=True
    )
    projected = project_artifact(
        source, output=tmp_path / "dictionary.sqlite3", profile="dictionary"
    )
    lexicon = Lexicon.from_path(projected)
    assert lexicon.topics("love") == ("names", "sports")
    with closing(sqlite3.connect(projected)) as connection:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(sense_topics)")]
        assert columns == ["topic", "sense_id"]
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='sense_search_terms'"
            ).fetchone()
            is None
        )
