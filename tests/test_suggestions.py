from __future__ import annotations

from pathlib import Path

import pytest

from lexhint import Lexicon, LexiconCapabilityError
from lexhint.builder import build_dictionary

FIXTURE = Path(__file__).parent / "fixtures" / "kaikki-mini.jsonl"


@pytest.fixture
def rich_artifact(tmp_path: Path) -> Path:
    path, _ = build_dictionary(
        "en", FIXTURE, output=tmp_path / "rich.sqlite3", profile="rich", no_frequency=True
    )
    return path


def test_suggest_is_distinct_from_prefix_completion(rich_artifact: Path) -> None:
    lexicon = Lexicon.from_path(rich_artifact)
    assert lexicon.complete("complier") == ()
    assert lexicon.suggest("complier") == ("compiler",)
    assert lexicon.suggest("compiler") == ("compiler",)


def test_suggest_validation_and_capability(rich_artifact: Path, tmp_path: Path) -> None:
    lexicon = Lexicon.from_path(rich_artifact)
    assert lexicon.suggest("", limit=20) == ()
    assert lexicon.suggest("compiler", limit=0) == ()
    with pytest.raises(ValueError):
        lexicon.suggest("compiler", limit=-1)
    with pytest.raises(ValueError):
        lexicon.suggest("compiler", max_distance=-1)

    lexical, _ = build_dictionary(
        "en",
        FIXTURE,
        output=tmp_path / "lexical.sqlite3",
        capabilities="lexical",
        no_frequency=True,
    )
    with pytest.raises(LexiconCapabilityError, match="search"):
        Lexicon.from_path(lexical).suggest("compiler")
