import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from lexhint import Dictionary, DictionaryIncompatible
from lexhint.builder import build_dictionary
from lexhint.store import semantic_rows

FIXTURE = Path(__file__).parent / "fixtures" / "kaikki-mini.jsonl"


def span(text: str, target: str) -> tuple[int, int]:
    start = text.index(target)
    return start, start + len(target)


def build(tmp_path: Path) -> Dictionary:
    path, stats = build_dictionary("en", FIXTURE, output=tmp_path / "en.sqlite3")
    assert stats.scanned_entries == 7
    assert stats.kept_entries == 5
    assert stats.words == 4
    assert stats.senses == 8
    return Dictionary.from_path(path)


def test_dictionary_parses_semantic_senses_and_topics(tmp_path: Path) -> None:
    dictionary = build(tmp_path)
    senses = dictionary.senses("scale")
    assert len(senses) == 2
    assert "music" in dictionary.topics("scale")
    assert "metrology" in dictionary.topics("scale")
    assert dictionary.senses("compiler")
    assert "computing" in dictionary.topics("compiler")
    assert dictionary.contains("banana")
    assert not dictionary.contains("metadataonly")


def test_gloss_bearing_senses_and_duplicates_are_stored(tmp_path: Path) -> None:
    dictionary = build(tmp_path)
    assert dictionary.senses("metadataonly") == ()
    assert dictionary.senses("compiler")[0].topics == ()
    assert len(dictionary.senses("compiler")) == 2


def love_entries() -> tuple[dict[str, object], ...]:
    return (
        {
            "word": "love",
            "lang_code": "en",
            "pos": "noun",
            "senses": [
                {"glosses": ["strong affection"]},
                {"glosses": ["a beloved person"]},
                {"glosses": ["Zero, no score."], "topics": ["sports"]},
            ],
        },
        {
            "word": "love",
            "lang_code": "en",
            "pos": "verb",
            "senses": [
                {"glosses": ["to feel strong affection"]},
                {"glosses": ["to like strongly"]},
            ],
        },
    )


def test_love_entries_keep_gloss_only_senses_and_topics() -> None:
    rows = [row for entry in love_entries() for row in semantic_rows(entry, language="en")]

    assert len(rows) == 5
    assert sum(bool(row.topics) for row in rows) == 1
    assert [row.pos for row in rows] == ["noun", "noun", "noun", "verb", "verb"]


def test_schema_columns_are_compact(tmp_path: Path) -> None:
    path, _ = build_dictionary("en", FIXTURE, output=tmp_path / "en.sqlite3")
    with closing(sqlite3.connect(path)) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(senses)")}
    assert columns == {"id", "word", "display_word", "pos", "glosses", "topics"}


def test_case_preference_is_consistent(tmp_path: Path) -> None:
    dictionary = build(tmp_path)
    assert dictionary.topics("house") == ("housing", "music")
    assert dictionary.topics("House") == ("politics",)
    assert dictionary.topics("HOUSE") == ("housing", "music", "politics")
    assert {sense.word for sense in dictionary.senses("house", all_case_variants=True)} == {
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
    scores = dictionary.topic_scores(text, target=span(text, "Am"))
    topics = {score.topic for score in scores}
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
    with pytest.raises(DictionaryIncompatible, match="schema 1; schema 4 is required"):
        Dictionary.from_path(path, language="en")


def test_wrong_language_is_incompatible(tmp_path: Path) -> None:
    path = tmp_path / "wrong-language.sqlite3"
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO metadata VALUES ('schema_version', '4')")
        connection.execute("INSERT INTO metadata VALUES ('language', 'de')")
        connection.commit()
    with pytest.raises(DictionaryIncompatible, match="language 'en' was requested"):
        Dictionary.from_path(path, language="en")


def test_from_path_can_assert_the_inferred_language(tmp_path: Path) -> None:
    path, _ = build_dictionary("en", FIXTURE, output=tmp_path / "en.sqlite3")
    assert Dictionary.from_path(path, language="en").language == "en"
