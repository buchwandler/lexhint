from __future__ import annotations

from pathlib import Path

import pytest

from lexhint import Lexicon
from lexhint.builder import build_dictionary


def _lexicon(tmp_path: Path) -> Lexicon:
    source = tmp_path / "words.jsonl"
    source.write_text(
        "".join(
            '{"word": "' + word + '", "lang_code": "en", "pos": "noun", '
            '"senses": [{"glosses": ["definition"]}]}\n'
            for word in ("love", "lover", "lovely", "loving", "compiler", "compare")
        ),
        encoding="utf-8",
    )
    path, _ = build_dictionary(
        "en", source, output=tmp_path / "en.sqlite3", capabilities="lexical", no_frequency=True
    )
    return Lexicon.from_path(path)


def test_suggest_returns_exact_then_prefixes_deterministically(tmp_path: Path) -> None:
    lexicon = _lexicon(tmp_path)

    assert lexicon.suggest("lov", limit=3) == ("love", "lover", "lovely")
    assert lexicon.suggest("LOVE") == ("love", "lover", "lovely", "loving")


def test_suggest_is_empty_for_blank_and_validates_limit(tmp_path: Path) -> None:
    lexicon = _lexicon(tmp_path)

    assert lexicon.suggest("   ") == ()
    assert lexicon.suggest("lov", limit=0) == ()
    with pytest.raises(ValueError, match="limit"):
        lexicon.suggest("lov", limit=-1)


def test_suggest_caps_results_and_is_prefix_bounded(tmp_path: Path) -> None:
    lexicon = _lexicon(tmp_path)

    assert len(lexicon.suggest("lov", limit=2)) == 2
    assert lexicon.suggest("com", limit=2) == ("compare", "compiler")
