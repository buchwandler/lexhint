import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from lexhint import Dictionary, DictionaryEntry, DictionaryIncompatible
from lexhint.builder import build_dictionary
from lexhint.models import Sense
from lexhint.store import create_schema, semantic_rows, set_metadata

FIXTURE = Path(__file__).parent / "fixtures" / "kaikki-mini.jsonl"


def span(text: str, target: str) -> tuple[int, int]:
    start = text.index(target)
    return start, start + len(target)


def build(tmp_path: Path) -> Dictionary:
    path, stats = build_dictionary("en", FIXTURE, output=tmp_path / "en.sqlite3")
    assert stats.scanned_entries == 7
    assert stats.kept_entries == 5
    assert stats.words == 4
    assert stats.senses == 9
    return Dictionary.from_path(path)


def test_dictionary_lookup_groups_ordered_rich_entries(tmp_path: Path) -> None:
    dictionary = build(tmp_path)
    entries = dictionary.lookup("scale")
    assert entries == (
        DictionaryEntry(
            "scale",
            "noun",
            (
                Sense(("A graduated measure.",), ("metrology",)),
                Sense(("A series of musical notes ordered by pitch.",), ("music",)),
            ),
        ),
    )
    assert len(dictionary.lookup("compiler")[0].senses) == 3
    assert dictionary.senses("compiler")[1].topics == ("computing",)
    assert dictionary.topics("compiler") == ("computing",)
    assert dictionary.contains("banana")
    assert not dictionary.contains("metadataonly")


def test_schema_v5_has_hierarchical_rich_tables(tmp_path: Path) -> None:
    path, _ = build_dictionary("en", FIXTURE, output=tmp_path / "en.sqlite3")
    with closing(sqlite3.connect(path)) as connection:
        entry_columns = {row[1] for row in connection.execute("PRAGMA table_info(entries)")}
        sense_columns = {row[1] for row in connection.execute("PRAGMA table_info(senses)")}
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
    assert entry_columns == {
        "id",
        "word",
        "display_word",
        "pos",
        "entry_index",
        "etymology",
        "forms",
        "pronunciations",
    }
    assert sense_columns == {
        "id",
        "entry_id",
        "sense_index",
        "glosses",
        "topics",
        "tags",
        "examples",
        "synonyms",
        "antonyms",
    }
    assert {"entries", "senses", "sense_topics", "lookups"} <= tables
    assert metadata["schema_version"] == "5"
    assert metadata["dictionary_profile"] == "rich"


def test_case_preference_is_consistent(tmp_path: Path) -> None:
    dictionary = build(tmp_path)
    assert dictionary.topics("house") == ("housing", "music")
    assert dictionary.topics("House") == ("politics",)
    assert dictionary.topics("HOUSE") == ("housing", "music", "politics")
    assert {entry.word for entry in dictionary.lookup("house", all_case_variants=True)} == {
        "house",
        "House",
    }


def test_music_context_is_dictionary_derived(tmp_path: Path) -> None:
    dictionary = build(tmp_path)
    text = "The scale is Am."
    support = dictionary.supports(text, target=span(text, "Am"), topic="music")
    assert support is not None
    assert support.topic == "music"
    assert "scale" in [cue.text.casefold() for cue in support.cues]


def test_software_context_is_dictionary_derived(tmp_path: Path) -> None:
    dictionary = build(tmp_path)
    text = "The compiler is 8.3.2."
    support = dictionary.supports(text, target=span(text, "8.3.2"), topic="computing")
    assert support is not None
    assert "compiler" in [cue.text.casefold() for cue in support.cues]


def test_context_does_not_leak_proper_name_topics(tmp_path: Path) -> None:
    dictionary = build(tmp_path)
    text = "The house track is Am."
    topics = {score.topic for score in dictionary.topic_scores(text, target=span(text, "Am"))}
    assert "music" in topics
    assert "politics" not in topics


def test_candidate_does_not_validate_itself(tmp_path: Path) -> None:
    dictionary = build(tmp_path)
    text = "scale"
    assert dictionary.supports(text, target=span(text, "scale"), topic="music") is None


def test_unrelated_context_fails_closed(tmp_path: Path) -> None:
    dictionary = build(tmp_path)
    text = "Am I late?"
    assert dictionary.supports(text, target=span(text, "Am"), topic="music") is None


def test_schema_incompatibility_is_controlled(tmp_path: Path) -> None:
    path = tmp_path / "schema-1.sqlite3"
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO metadata VALUES ('schema_version', '1')")
        connection.execute("INSERT INTO metadata VALUES ('language', 'en')")
        connection.commit()
    with pytest.raises(DictionaryIncompatible, match="schema 1; schema 5 is required"):
        Dictionary.from_path(path, language="en")


def test_wrong_language_is_incompatible(tmp_path: Path) -> None:
    path = tmp_path / "wrong-language.sqlite3"
    with closing(sqlite3.connect(path)) as connection:
        create_schema(connection)
        set_metadata(connection, {"schema_version": "5", "language": "de", "coverage": "full"})
        connection.commit()
    with pytest.raises(DictionaryIncompatible, match="language 'en' was requested"):
        Dictionary.from_path(path, language="en")


def test_from_path_can_assert_the_inferred_language(tmp_path: Path) -> None:
    path, _ = build_dictionary("en", FIXTURE, output=tmp_path / "en.sqlite3")
    assert Dictionary.from_path(path, language="en").language == "en"


def test_semantic_projection_keeps_duplicate_and_gloss_only_senses() -> None:
    entry = {
        "word": "love",
        "lang_code": "en",
        "pos": "noun",
        "senses": [
            {"glosses": ["strong affection"]},
            {"glosses": ["Zero, no score."], "topics": ["sports"]},
        ],
    }
    rows = tuple(semantic_rows(entry, language="en"))
    assert rows[0].glosses == ("strong affection",)
    assert rows[1].topics == ("sports",)
