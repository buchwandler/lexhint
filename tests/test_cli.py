from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from lexhint import cli
from lexhint.models import LexicalSegment

FIXTURE = Path(__file__).parent / "fixtures" / "kaikki-mini.jsonl"


class FakeLexicon:
    def __init__(self, language: str, **_: object) -> None:
        self.language = language

    def rank(self, word: str) -> int | None:
        return 213 if word.casefold() == "house" else None

    def segment(self, text: str) -> tuple[LexicalSegment, ...]:
        assert text == "chatgpt"
        return (LexicalSegment("chat", True, 2668), LexicalSegment("gpt", False))


def test_word_uses_default_english(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "Lexicon", FakeLexicon)
    assert cli.main(["word", "house"]) == 0
    assert capsys.readouterr().out == "house  ✓ known  rank #213\n"


def test_legacy_word_language_still_works(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "Lexicon", FakeLexicon)
    assert cli.main(["word", "de", "house", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["language"] == "de"
    assert payload["word"] == "house"


def test_segment_human_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "Lexicon", FakeLexicon)
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


def test_dictionary_json_uses_schema_v2_shape(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "en.sqlite3"
    assert cli.main(["dictionary", "build", "en", str(FIXTURE), "--output", str(output)]) == 0
    capsys.readouterr()
    assert cli.main(["--json", "dictionary", "word", "en", "compiler", "--path", str(output)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["senses"]
    assert set(payload["senses"][0]) == {"word", "pos", "glosses", "topics"}


def test_missing_wordlist_is_runtime_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("LEXHINT_CACHE_DIR", str(tmp_path / "empty"))
    assert cli.main(["word", "house"]) == 1
    error = capsys.readouterr().err
    assert "no word list installed" in error
    assert "lexhint setup" in error


def test_invalid_environment_language_is_runtime_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("LEXHINT_LANGUAGE", "xx")
    assert cli.main(["word", "house"]) == 1
    assert "unsupported language" in capsys.readouterr().err


def test_schema_incompatibility_has_rebuild_hint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "schema-1.sqlite3"
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO metadata VALUES ('schema_version', '1')")
        connection.execute("INSERT INTO metadata VALUES ('language', 'en')")
        connection.commit()
    assert cli.main(["dictionary", "word", "en", "compiler", "--path", str(path)]) == 1
    error = capsys.readouterr().err
    assert "schema 1" in error
    assert "lexhint dictionary build" in error
