from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from lexhint.builder import build_dictionary
from lexhint.cli import main

FIXTURE = Path(__file__).parent / "fixtures" / "kaikki-rich.jsonl"


@pytest.fixture
def rich_artifact(tmp_path: Path) -> Path:
    path, _ = build_dictionary(
        "en",
        FIXTURE,
        output=tmp_path / "en.sqlite3",
        no_frequency=True,
    )
    return path


def dictionary_args(path: Path, *extra: str) -> list[str]:
    return ["dictionary", "word", "love", "--path", str(path), *extra]


def test_default_dictionary_output_is_standard(
    rich_artifact: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(dictionary_args(rich_artifact)) == 0

    output = capsys.readouterr().out
    assert "\x1b[" not in output
    assert "love" in output
    assert "    1. A strong feeling of affection." in output
    assert "    2. Zero score in tennis." in output
    assert "    3. To have strong affection for." in output
    assert "tags: uncountable" in output
    assert "topics: sports" in output
    assert "forms: loves" in output
    assert "[lʌv] [US]" in output
    assert "etymology:" not in output
    assert "example:" not in output
    assert "translation:" not in output
    assert "synonyms:" not in output
    assert "antonyms:" not in output
    assert "Love.ogg" not in output


def test_compact_dictionary_output_is_reduced(
    rich_artifact: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(dictionary_args(rich_artifact, "--detail", "compact")) == 0

    output = capsys.readouterr().out
    assert "love" in output
    assert "  noun" in output
    assert "A strong feeling of affection." in output
    assert "tags:" not in output
    assert "topics:" not in output
    assert "forms:" not in output
    assert "pronunciation:" not in output
    assert "etymology:" not in output
    assert "example:" not in output
    assert "synonyms:" not in output
    assert "antonyms:" not in output


def test_full_dictionary_output_exposes_retained_fields(
    rich_artifact: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(dictionary_args(rich_artifact, "--detail", "full")) == 0

    output = capsys.readouterr().out
    for value in (
        "From Middle English love.",
        "A strong feeling of affection.",
        "tags: uncountable",
        "Their love grew over time.",
        "translation: Ihre Liebe wuchs.",
        "synonyms:",
        "affection",
        "antonyms:",
        "hate",
        "loves [plural]",
        "[lʌv] [US]",
        "Zero score in tennis.",
        "topics: sports",
        "To have strong affection for.",
    ):
        assert value in output
    assert "Love.ogg" not in output


def test_dictionary_json_remains_complete(
    rich_artifact: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--json", *dictionary_args(rich_artifact)]) == 0

    payload = json.loads(capsys.readouterr().out)
    first_entry = payload["entries"][0]
    assert first_entry["etymology"] == "From Middle English love."
    assert first_entry["forms"] == [{"form": "loves", "tags": ["plural"]}]
    assert first_entry["pronunciations"] == [{"ipa": "/lʌv/", "tags": ["US"]}]
    assert first_entry["senses"][0]["tags"] == ["uncountable"]
    assert first_entry["senses"][0]["examples"] == [
        {"text": "Their love grew over time.", "translation": "Ihre Liebe wuchs."}
    ]
    assert first_entry["senses"][0]["synonyms"] == ["affection"]
    assert first_entry["senses"][0]["antonyms"] == ["hate"]


def test_detail_is_rejected_with_json(
    rich_artifact: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--json", *dictionary_args(rich_artifact, "--detail", "full")]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "--detail only applies to human-readable output" in captured.err


def test_dictionary_lookup_preserves_case_and_no_entry_behavior(
    rich_artifact: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(dictionary_args(rich_artifact, "--detail", "full").copy()) == 0
    capsys.readouterr()

    assert main(["dictionary", "word", "Love", "--path", str(rich_artifact)]) == 0
    case_output = capsys.readouterr().out
    assert "Love" in case_output
    assert "A surname." in case_output
    assert "A strong feeling of affection." not in case_output

    assert main(["dictionary", "word", "missing", "--path", str(rich_artifact)]) == 0
    missing_output = capsys.readouterr().out
    assert "no dictionary entries found" in missing_output


def test_dictionary_field_overlays_are_repeatable(
    rich_artifact: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(
            dictionary_args(
                rich_artifact,
                "--detail",
                "compact",
                "--show",
                "example",
                "--show",
                "synonym",
            )
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "examples" in output
    assert "Their love grew over time." in output
    assert "synonyms: affection" in output
    assert "tags:" not in output

    assert (
        main(
            dictionary_args(
                rich_artifact,
                "--detail",
                "full",
                "--hide",
                "examples,tags,etymology",
            )
        )
        == 0
    )

    output = capsys.readouterr().out
    assert "etymology" not in output
    assert "examples" not in output
    assert "tags:" not in output


def test_dictionary_pos_filters_select_entries(
    rich_artifact: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(dictionary_args(rich_artifact, "--pos", "noun,verb")) == 0
    output = capsys.readouterr().out
    assert "  noun" in output
    assert "  verb" in output
    assert "Proper Noun" not in output

    assert main(dictionary_args(rich_artifact, "--exclude-pos", "verb")) == 0
    output = capsys.readouterr().out
    assert "  verb" not in output
    assert "  noun" in output


def test_dictionary_pos_filters_apply_to_json_and_reject_human_options(
    rich_artifact: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--json", *dictionary_args(rich_artifact, "--pos", "NOUN")]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert [entry["pos"] for entry in payload["entries"]] == ["noun", "noun"]

    assert main(["--json", *dictionary_args(rich_artifact, "--hide", "examples")]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "cannot be used with --json" in captured.err


def test_dictionary_pos_empty_result_is_explained(
    rich_artifact: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(dictionary_args(rich_artifact, "--pos", "adjective")) == 0
    output = capsys.readouterr().out
    assert "no dictionary entries matched --pos adjective" in output


def test_dictionary_tty_output_uses_color(
    rich_artifact: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)

    assert main(dictionary_args(rich_artifact, "--detail", "full")) == 0
    assert "\x1b[" in capsys.readouterr().out


def test_dictionary_no_color_options_disable_tty_color(
    rich_artifact: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)

    assert main(["--no-color", *dictionary_args(rich_artifact)]) == 0
    assert "\x1b[" not in capsys.readouterr().out

    monkeypatch.setenv("NO_COLOR", "1")
    assert main(dictionary_args(rich_artifact)) == 0
    assert "\x1b[" not in capsys.readouterr().out


def test_dictionary_json_never_contains_ansi_on_tty(
    rich_artifact: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)

    assert main(["--json", *dictionary_args(rich_artifact)]) == 0
    raw = capsys.readouterr().out
    assert "\x1b[" not in raw
    assert json.loads(raw)["entries"]
