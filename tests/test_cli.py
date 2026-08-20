from __future__ import annotations

import json
from pathlib import Path

import pytest

from lexhint import cli
from lexhint.models import LexicalSegment, WordInfo

FIXTURE = Path(__file__).parent / "fixtures" / "kaikki-mini.jsonl"


class FakeDictionary:
    def __init__(self, language: str, **_: object) -> None:
        self.language = language

    def word_info(self, word: str) -> WordInfo:
        return WordInfo(
            word, word.casefold() == "house", 213 if word.casefold() == "house" else None, 42
        )

    def segment(self, text: str) -> tuple[LexicalSegment, ...]:
        assert text == "chatgpt"
        return (LexicalSegment("chat", True, 2668), LexicalSegment("gpt", False))


def test_word_uses_dictionary_and_reports_frequency_fields(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "Dictionary", FakeDictionary)
    assert cli.main(["word", "house"]) == 0
    assert "house  ✓ known" in capsys.readouterr().out


def test_word_json_separates_membership_from_frequency(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "Dictionary", FakeDictionary)
    assert cli.main(["--json", "word", "house"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "language": "en",
        "word": "house",
        "known": True,
        "frequency_rank": 213,
        "frequency_count": 42,
    }


def test_segment_human_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "Dictionary", FakeDictionary)
    assert cli.main(["segment", "chatgpt"]) == 0
    output = capsys.readouterr().out
    assert "chatgpt" in output
    assert "chat" in output
    assert "gpt" in output
    assert "unknown" in output


def test_dictionary_build_source_defaults_to_kaikki() -> None:
    args = cli._parser().parse_args(["dictionary", "build", "en"])
    assert args.source == cli.KAIKKI_RAW_URL
    assert not hasattr(args, "limit")
    assert not hasattr(args, "auto_fetch_wordlist")
    assert not hasattr(args, "force")


def test_setup_has_no_wordlist_command() -> None:
    with pytest.raises(SystemExit):
        cli._parser().parse_args(["fetch", "en"])


def test_schema_incompatibility_has_rebuild_hint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import sqlite3

    path = tmp_path / "schema-1.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO metadata VALUES ('schema_version', '1')")
        connection.execute("INSERT INTO metadata VALUES ('language', 'en')")
        connection.commit()
    assert cli.main(["dictionary", "word", "en", "compiler", "--path", str(path)]) == 1
    error = capsys.readouterr().err
    assert "schema 1" in error
    assert "lexhint dictionary build" in error
