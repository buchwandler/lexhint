from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from lexhint import Dictionary, DictionaryIncompatible
from lexhint import dictionary as dictionary_module
from lexhint.builder import build_dictionary
from lexhint.dictionary import DictionaryFetchResult, DictionaryWordNotFound, fetch_dictionary_word
from lexhint.store import create_schema, replace_word_rows, set_metadata

FIXTURE = Path(__file__).parent / "fixtures" / "kaikki-mini.jsonl"


def entry(word: str, topic: str | None, *, lang_code: str = "en") -> dict[str, object]:
    sense: dict[str, object] = {"glosses": [f"gloss for {word}"]}
    if topic is not None:
        sense["topics"] = [topic]
    return {"word": word, "lang_code": lang_code, "pos": "noun", "senses": [sense]}


def test_incremental_fetch_accumulates_and_hits_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "en.sqlite3"
    calls: list[str] = []

    def fake_fetch(word: str, *, timeout: float) -> tuple[dict[str, object], ...]:
        calls.append(word)
        return (entry(word, {"compiler": "computing", "scale": "music"}[word]),)

    monkeypatch.setattr(dictionary_module, "fetch_word_entries", fake_fetch)
    assert fetch_dictionary_word("en", "compiler", path=path).status == "fetched"
    assert fetch_dictionary_word("en", "scale", path=path).status == "fetched"
    assert fetch_dictionary_word("en", "compiler", path=path).status == "cached"
    assert calls == ["compiler", "scale"]

    dictionary = Dictionary("en", path=path)
    assert dictionary.topics("compiler") == ("computing",)
    assert dictionary.topics("scale") == ("music",)

    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM lookups").fetchone() == (2,)
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        assert metadata["coverage"] == "partial"
        assert metadata["source_mode"] == "live-partial"
        assert metadata["snapshot_id"] == "partial-cache"


def test_empty_and_not_found_lookups_are_cached(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "en.sqlite3"
    calls: list[str] = []

    def fake_fetch(word: str, *, timeout: float) -> tuple[dict[str, object], ...]:
        calls.append(word)
        if word == "missing":
            raise DictionaryWordNotFound("missing")
        return (entry(word, None),)

    monkeypatch.setattr(dictionary_module, "fetch_word_entries", fake_fetch)
    assert fetch_dictionary_word("en", "ordinary", path=path).senses == 1
    assert fetch_dictionary_word("en", "ordinary", path=path).status == "cached"
    assert fetch_dictionary_word("en", "missing", path=path).status == "not_found"
    assert fetch_dictionary_word("en", "missing", path=path).status == "cached"
    assert calls == ["ordinary", "missing"]

    with closing(sqlite3.connect(path)) as connection:
        statuses = dict(connection.execute("SELECT query, status FROM lookups"))
    assert statuses == {"ordinary": "complete", "missing": "not_found"}


def test_refresh_replaces_exact_case_page(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "en.sqlite3"
    topics = {"house": "housing", "House": "politics"}

    def fake_fetch(word: str, *, timeout: float) -> tuple[dict[str, object], ...]:
        return (entry(word, topics[word]),)

    monkeypatch.setattr(dictionary_module, "fetch_word_entries", fake_fetch)
    fetch_dictionary_word("en", "house", path=path)
    fetch_dictionary_word("en", "House", path=path)
    dictionary = Dictionary("en", path=path)
    assert dictionary.topics("house") == ("housing",)
    assert dictionary.topics("House") == ("politics",)

    topics["house"] = "architecture"
    result = fetch_dictionary_word("en", "house", path=path, refresh=True)
    assert result == DictionaryFetchResult("house", "fetched", 1, result.source_url, False)
    assert Dictionary("en", path=path).topics("house") == ("architecture",)


def test_full_coverage_is_authoritative(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path, _ = build_dictionary("en", FIXTURE, output=tmp_path / "en.sqlite3")
    monkeypatch.setattr(
        dictionary_module,
        "fetch_word_entries",
        lambda word, *, timeout: pytest.fail("full coverage must not fetch"),
    )
    result = fetch_dictionary_word("en", "not-in-snapshot", path=path)
    assert result.status == "covered"


def test_lazy_fetch_keeps_all_love_senses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "en.sqlite3"
    entries = (
        {
            "word": "love",
            "lang_code": "en",
            "pos": "noun",
            "senses": [
                {"glosses": ["strong affection"]},
                {"glosses": ["Zero, no score."], "topics": ["sports"]},
            ],
        },
        {
            "word": "love",
            "lang_code": "en",
            "pos": "verb",
            "senses": [{"glosses": ["to feel strong affection"]}],
        },
    )
    monkeypatch.setattr(dictionary_module, "fetch_word_entries", lambda word, *, timeout: entries)

    result = fetch_dictionary_word("en", "love", path=path)
    dictionary = Dictionary("en", path=path)

    assert result.senses == 3
    assert len(dictionary.senses("love")) == 3
    assert dictionary.topics("love") == ("sports",)


def test_schema_v3_partial_cache_is_invalidated(tmp_path: Path) -> None:
    path = tmp_path / "v3-partial.sqlite3"
    with closing(sqlite3.connect(path)) as connection:
        create_schema(connection)
        set_metadata(
            connection,
            {"schema_version": "3", "language": "en", "coverage": "partial"},
        )
        connection.commit()
    replace_word_rows(
        path,
        language="en",
        query="love",
        source_url="https://example.test/love",
        entries=(entry("love", "sports"),),
    )

    dictionary = Dictionary("en", path=path)

    with closing(sqlite3.connect(path)) as connection:
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        assert metadata["schema_version"] == "4"
        assert connection.execute("SELECT COUNT(*) FROM senses").fetchone() == (0,)
        assert connection.execute("SELECT COUNT(*) FROM lookups").fetchone() == (0,)
    assert dictionary.senses("love") == ()


def test_schema_v3_full_cache_requires_rebuild(tmp_path: Path) -> None:
    path = tmp_path / "v3-full.sqlite3"
    with closing(sqlite3.connect(path)) as connection:
        create_schema(connection)
        set_metadata(
            connection,
            {"schema_version": "3", "language": "en", "coverage": "full"},
        )
        connection.commit()

    with pytest.raises(DictionaryIncompatible, match="schema 3.*rebuild"):
        Dictionary.from_path(path, language="en")
