from __future__ import annotations

import json

import pytest

from lexhint import cli
from lexhint.models import Segment


class FakeLexicon:
    def __init__(self, language: str, **_: object) -> None:
        self.language = language

    def rank(self, word: str) -> int | None:
        return 213 if word.casefold() == "house" else None

    def segment(self, text: str) -> tuple[Segment, ...]:
        assert text == "chatgpt"
        return (Segment("chat", True, 2668), Segment("gpt", False))


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
    assert args.auto_fetch_wordlist is True
