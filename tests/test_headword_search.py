from __future__ import annotations

from pathlib import Path

import pytest

from lexhint import Lexicon
from lexhint.builder import build_dictionary

FIXTURE = Path(__file__).parent / "fixtures" / "kaikki-mini.jsonl"


@pytest.fixture
def lexical_artifact(tmp_path: Path) -> Path:
    path, _ = build_dictionary(
        "en",
        FIXTURE,
        output=tmp_path / "lexical.sqlite3",
        capabilities="lexical",
        no_frequency=True,
    )
    return path


def test_glob_and_regex_headword_matching(lexical_artifact: Path) -> None:
    lexicon = Lexicon.from_path(lexical_artifact)
    assert lexicon.match_headwords("comp*") == ("compiler",)
    assert lexicon.match_headwords("*er") == ("compiler",)
    assert lexicon.match_headwords("^comp.*er$", syntax="regex") == ("compiler",)
    assert lexicon.match_headwords("colou?r", syntax="regex") == ()


def test_headword_validation_and_determinism(lexical_artifact: Path) -> None:
    lexicon = Lexicon.from_path(lexical_artifact)
    assert lexicon.match_headwords("*", limit=0) == ()
    with pytest.raises(ValueError):
        lexicon.match_headwords("*", limit=-1)
    with pytest.raises(ValueError):
        lexicon.match_headwords("*", syntax="sql")
    with pytest.raises(ValueError, match="invalid regex"):
        lexicon.match_headwords("[", syntax="regex")
    assert lexicon.match_headwords("*", limit=2) == ("banana", "compiler")
