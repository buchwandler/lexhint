from __future__ import annotations

from pathlib import Path

import pytest

from lexhint import DictionarySearchHit, Lexicon, LexiconCapabilityError
from lexhint.builder import build_dictionary

FIXTURE = Path(__file__).parent / "fixtures" / "kaikki-mini.jsonl"


@pytest.fixture
def rich_artifact(tmp_path: Path) -> Path:
    path, _ = build_dictionary(
        "en", FIXTURE, output=tmp_path / "rich.sqlite3", profile="rich", no_frequency=True
    )
    return path


def test_dictionary_search_returns_bounded_hits(rich_artifact: Path) -> None:
    lexicon = Lexicon.from_path(rich_artifact)
    hits = lexicon.search_definitions("computer program", fields=("glosses",), match="all")
    assert hits
    assert isinstance(hits[0], DictionarySearchHit)
    assert hits[0].word == "compiler"
    assert hits[0].matched_terms == ("computer", "program")
    assert hits[0].matched_fields == ("glosses",)
    assert hits[0].score > 0


def test_dictionary_search_fields_modes_and_reverse(rich_artifact: Path) -> None:
    lexicon = Lexicon.from_path(rich_artifact)
    assert lexicon.search_definitions("music", fields=("topics",))
    assert lexicon.search_definitions("computer music", match="any")
    assert lexicon.search_definitions("computer", fields=("examples",)) == ()
    assert lexicon.reverse("computer program")[0].word == "compiler"
    assert lexicon.search_definitions("", limit=20) == ()


def test_dictionary_search_validation_and_capability(rich_artifact: Path, tmp_path: Path) -> None:
    lexicon = Lexicon.from_path(rich_artifact)
    with pytest.raises(ValueError):
        lexicon.search_definitions("word", limit=-1)
    with pytest.raises(ValueError):
        lexicon.search_definitions("word", fields=("missing",))
    with pytest.raises(ValueError):
        lexicon.search_definitions("word", match="none")

    lexical_search, _ = build_dictionary(
        "en",
        FIXTURE,
        output=tmp_path / "lexical-search.sqlite3",
        capabilities="lexical,search",
        no_frequency=True,
    )
    with pytest.raises(LexiconCapabilityError, match="dictionary"):
        Lexicon.from_path(lexical_search).search_definitions("compiler")
