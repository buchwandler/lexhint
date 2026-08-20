from __future__ import annotations

import json
from pathlib import Path

import pytest

from lexhint import cli
from lexhint import dictionary as dictionary_module


def entry(word: str, topic: str) -> dict[str, object]:
    return {
        "word": word,
        "lang_code": "en",
        "pos": "noun",
        "senses": [{"glosses": [word], "topics": [topic]}],
    }


def test_dictionary_fetch_and_offline_word_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "en.sqlite3"

    def fake_fetch(word: str, *, timeout: float) -> tuple[dict[str, object], ...]:
        return (entry(word, "computing"),)

    monkeypatch.setattr(dictionary_module, "fetch_word_entries", fake_fetch)
    assert cli.main(["dictionary", "fetch", "en", "compiler", "--path", str(path)]) == 0
    output = capsys.readouterr().out
    assert "compiler" in output
    assert "dictionary senses" in output

    assert cli.main(["--offline", "dictionary", "word", "en", "compiler", "--path", str(path)]) == 0
    output = capsys.readouterr().out
    assert "computing" in output


def test_dictionary_fetch_json_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "en.sqlite3"
    monkeypatch.setattr(
        dictionary_module,
        "fetch_word_entries",
        lambda word, *, timeout: (entry(word, "computing"),),
    )
    assert cli.main(["--json", "dictionary", "fetch", "compiler", "--path", str(path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["language"] == "en"
    assert payload["results"][0]["status"] == "fetched"
    assert payload["results"][0]["senses"] == 1


def test_offline_missing_dictionary_word_fails_clearly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "empty.sqlite3"
    assert cli.main(["--offline", "dictionary", "word", "compiler", "--path", str(path)]) == 1
    error = capsys.readouterr().err
    assert "not cached" in error
    assert "dictionary fetch" in error


def test_dictionary_word_shows_gloss_only_and_topic_senses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
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
    monkeypatch.setattr(
        dictionary_module,
        "fetch_word_entries",
        lambda word, *, timeout: entries,
    )

    assert cli.main(["dictionary", "fetch", "en", "love", "--path", str(path)]) == 0
    capsys.readouterr()
    assert cli.main(["dictionary", "word", "en", "love", "--path", str(path)]) == 0
    output = capsys.readouterr().out
    assert "strong affection" in output
    assert "Zero, no score." in output
    assert "sports" in output
    assert "to feel strong affection" in output


def test_dictionary_word_json_keeps_empty_topics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "en.sqlite3"
    monkeypatch.setattr(
        dictionary_module,
        "fetch_word_entries",
        lambda word, *, timeout: (
            {
                "word": "love",
                "lang_code": "en",
                "pos": "noun",
                "senses": [{"glosses": ["strong affection"]}],
            },
        ),
    )

    assert cli.main(["--json", "dictionary", "word", "en", "love", "--path", str(path)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["language"] == "en"
    assert payload["word"] == "love"
    assert payload["entries"] == [
        {
            "word": "love",
            "pos": "noun",
            "senses": [
                {
                    "glosses": ["strong affection"],
                    "topics": [],
                    "tags": [],
                    "examples": [],
                    "synonyms": [],
                    "antonyms": [],
                }
            ],
            "forms": [],
            "pronunciations": [],
            "etymology": None,
        }
    ]
