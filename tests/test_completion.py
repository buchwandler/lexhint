from __future__ import annotations

import json
from pathlib import Path

import pytest

from lexhint import Lexicon
from lexhint.builder import build_dictionary
from lexhint.cli import main
from lexhint.lexicon import _prefix_upper_bound


def _lexicon(
    tmp_path: Path,
    words: tuple[str, ...],
    *,
    frequency: str | None = None,
) -> Lexicon:
    source = tmp_path / "words.jsonl"
    source.write_text(
        "".join(
            json.dumps(
                {
                    "word": word,
                    "lang_code": "en",
                    "pos": "noun",
                    "senses": [{"glosses": ["definition"]}],
                }
            )
            + "\n"
            for word in words
        ),
        encoding="utf-8",
    )
    frequency_path = None
    if frequency is not None:
        frequency_path = tmp_path / "frequency.txt"
        frequency_path.write_text(frequency, encoding="utf-8")
    path, _ = build_dictionary(
        "en",
        source,
        output=tmp_path / "en.sqlite3",
        capabilities="lexical",
        frequency_source=frequency_path,
        no_frequency=frequency_path is None,
    )
    return Lexicon.from_path(path)


def test_complete_returns_exact_then_full_prefixes_deterministically(tmp_path: Path) -> None:
    lexicon = _lexicon(tmp_path, ("love", "lover", "lovely", "loving", "compiler"))

    assert lexicon.complete("love") == ("love", "lovely", "lover")
    assert lexicon.complete("LOVE", limit=1) == ("love",)
    assert all(value.startswith("love") for value in lexicon.complete("love"))
    assert "loving" not in lexicon.complete("love")


def test_complete_does_not_correct_typos_or_use_partial_fuzzy_buckets(tmp_path: Path) -> None:
    lexicon = _lexicon(tmp_path, ("love", "lover", "compiler"))

    assert lexicon.complete("lvoe") == ()
    assert lexicon.complete("xompiler") == ()
    assert lexicon.complete("compilet") == ()


def test_complete_exact_match_survives_a_crowded_prefix(tmp_path: Path) -> None:
    words = tuple(f"abc{index:03d}" for index in range(201)) + ("abczzzz",)
    lexicon = _lexicon(tmp_path, words)

    assert lexicon.complete("abczzzz", limit=1) == ("abczzzz",)


def test_complete_handles_empty_and_invalid_limits(tmp_path: Path) -> None:
    lexicon = _lexicon(tmp_path, ("love",))

    assert lexicon.complete("") == ()
    assert lexicon.complete("   ") == ()
    assert lexicon.complete("lov", limit=0) == ()
    with pytest.raises(ValueError, match="limit"):
        lexicon.complete("lov", limit=-1)


def test_complete_uses_corpus_rank_when_frequency_is_available(tmp_path: Path) -> None:
    lexicon = _lexicon(
        tmp_path,
        ("compiler", "compact", "compass"),
        frequency="compact 10\ncompiler 20\ncompass 30\n",
    )

    assert lexicon.complete("comp") == ("compact", "compiler", "compass")


def test_complete_uses_lexical_order_without_frequency(tmp_path: Path) -> None:
    lexicon = _lexicon(tmp_path, ("compiler", "compact", "compass"))

    assert lexicon.complete("comp") == ("compact", "compass", "compiler")


def test_prefix_upper_bound_and_unicode_completion(tmp_path: Path) -> None:
    assert _prefix_upper_bound("abc") == "abd"
    assert _prefix_upper_bound("a\U0010ffff") == "b"
    lexicon = _lexicon(tmp_path, ("café", "caféteria", "caffè", "caz"))

    assert lexicon.complete("CAFÉ") == ("café", "caféteria")


def test_complete_treats_like_metacharacters_as_literal_text(tmp_path: Path) -> None:
    lexicon = _lexicon(tmp_path, ("100%", "100%proof", "100_", "100_\\word"))

    assert lexicon.complete("100%") == ("100%", "100%proof")
    assert lexicon.complete("100_") == ("100_", "100_\\word")


def test_complete_cli_human_and_json_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lexicon = _lexicon(tmp_path, ("love", "lover", "lovely", "loving"))

    assert main(["complete", "lov", "--limit", "2", "--path", str(lexicon.path)]) == 0
    assert capsys.readouterr().out.splitlines() == ["love", "lovely"]

    assert main(["--json", "complete", "LOV", "--limit", "2", "--path", str(lexicon.path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "language": "en",
        "prefix": "lov",
        "completions": ["love", "lovely"],
    }
