import json
from pathlib import Path

import pytest

from lexhint import Dictionary, cli
from lexhint import dictionary as dictionary_module
from lexhint.builder import build_dictionary
from lexhint.dictionary import fetch_dictionary_word

FIXTURE = Path(__file__).parent / "fixtures" / "kaikki-rich.jsonl"


def test_full_build_preserves_rich_entries_and_homograph_order(tmp_path: Path) -> None:
    path, stats = build_dictionary("en", FIXTURE, output=tmp_path / "en.sqlite3")
    dictionary = Dictionary.from_path(path)

    assert stats.kept_entries == 4
    assert stats.words == 1
    assert stats.senses == 4
    entries = dictionary.lookup("love")
    assert [entry.pos for entry in entries] == ["noun", "noun", "verb"]
    assert entries[0].etymology == "From Middle English love."
    assert entries[1].etymology == "A separate tennis sense."
    assert entries[0].forms[0].form == "loves"
    assert entries[0].pronunciations[0].ipa == "/lʌv/"
    assert entries[0].senses[0].examples[0].translation == "Ihre Liebe wuchs."
    assert entries[0].senses[0].synonyms == ("affection",)
    assert entries[0].senses[0].antonyms == ("hate",)
    assert dictionary.topics("love") == ("sports",)
    assert dictionary.lookup("Love")[0].pos == "proper noun"


def test_lazy_and_full_paths_produce_equivalent_rich_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    full_path, _ = build_dictionary("en", FIXTURE, output=tmp_path / "full.sqlite3")
    full_entries = Dictionary.from_path(full_path).lookup("love", all_case_variants=True)

    lazy_path = tmp_path / "lazy.sqlite3"
    raw_entries = tuple(
        json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines() if line
    )
    monkeypatch.setattr(
        dictionary_module,
        "fetch_word_entries",
        lambda word, *, timeout: tuple(raw_entries[:3]),
    )
    fetch_dictionary_word("en", "love", path=lazy_path)

    assert Dictionary("en", path=lazy_path).lookup("love") == full_entries[:3]


def test_cli_human_output_includes_rich_sections(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path, _ = build_dictionary("en", FIXTURE, output=tmp_path / "en.sqlite3")
    assert cli.main(["dictionary", "word", "love", "--path", str(path)]) == 0
    output = capsys.readouterr().out
    assert "A strong feeling of affection." in output
    assert "uncountable" in output
    assert "Their love grew over time." in output
    assert "/lʌv/" in output
    assert "loves" in output
    assert "Love.ogg" not in output
    assert ".wav" not in output
    assert "affection" in output
