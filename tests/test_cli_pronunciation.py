from __future__ import annotations

import json
from pathlib import Path

import pytest

from lexhint.builder import build_dictionary
from lexhint.cli import main


@pytest.fixture
def pronunciation_artifact(tmp_path: Path) -> Path:
    source = tmp_path / "pronunciations.jsonl"
    source.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "word": "love",
                        "lang_code": "en",
                        "pos": "noun",
                        "sounds": [
                            {
                                "ipa": "/multi/",
                                "tags": ["Canada", "General-American", "Received-Pronunciation"],
                            },
                            {
                                "ipa": "/multi/",
                                "tags": ["Canada", "General-American", "Received-Pronunciation"],
                            },
                            {"ipa": "/neutral/", "tags": []},
                        ],
                        "senses": [{"glosses": ["not shown"]}],
                    }
                ),
                json.dumps(
                    {
                        "word": "love",
                        "lang_code": "en",
                        "pos": "noun",
                        "sounds": [
                            {
                                "ipa": "/multi/",
                                "tags": ["Canada", "General-American", "Received-Pronunciation"],
                            }
                        ],
                        "senses": [{"glosses": ["not shown"]}],
                    }
                ),
                json.dumps(
                    {
                        "word": "love",
                        "lang_code": "en",
                        "pos": "verb",
                        "sounds": [
                            {
                                "ipa": "/multi/",
                                "tags": ["Canada", "General-American", "Received-Pronunciation"],
                            }
                        ],
                        "senses": [{"glosses": ["not shown"]}],
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    artifact, _ = build_dictionary(
        "en",
        source,
        output=tmp_path / "pronunciations.sqlite3",
        capabilities="lexical,dictionary",
        no_frequency=True,
    )
    return artifact


def cli_args(path: Path, *extra: str) -> list[str]:
    return ["dictionary", "pronunciation", "love", "--path", str(path), *extra]


def test_human_pronunciation_output_is_grouped_and_focused(
    pronunciation_artifact: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(cli_args(pronunciation_artifact, "--region", "Canada")) == 0

    output = capsys.readouterr().out
    assert output.splitlines() == [
        "love",
        "  noun",
        "    /multi/ [Canada, General-American, Received-Pronunciation]",
        "  verb",
        "    /multi/ [Canada, General-American, Received-Pronunciation]",
    ]
    assert "not shown" not in output


def test_cli_locale_json_is_canonical_and_preserves_tags(
    pronunciation_artifact: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--json", *cli_args(pronunciation_artifact, "--locale", "en_GB")]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["language"] == "en"
    assert payload["locale"] == "GB"
    assert payload["region"] is None
    assert payload["include_neutral"] is False
    assert payload["entries"][0]["pos"] == "noun"
    assert payload["entries"][0]["pronunciations"] == [
        {
            "ipa": "/multi/",
            "tags": ["Canada", "General-American", "Received-Pronunciation"],
        }
    ]
    assert "\x1b[" not in capsys.readouterr().out


def test_cli_pos_and_neutral_validation(
    pronunciation_artifact: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(cli_args(pronunciation_artifact, "--region", "Canada", "--pos", "noun")) == 0
    assert "  verb" not in capsys.readouterr().out

    assert main(cli_args(pronunciation_artifact, "--include-neutral")) == 1
    assert "requires --region or --locale" in capsys.readouterr().err


def test_cli_rejects_region_and_locale_together(pronunciation_artifact: Path) -> None:
    with pytest.raises(SystemExit, match="2"):
        main(cli_args(pronunciation_artifact, "--region", "Canada", "--locale", "en_US"))


def test_cli_empty_filtered_result_is_success(
    pronunciation_artifact: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(cli_args(pronunciation_artifact, "--region", "Central-American")) == 0
    output = capsys.readouterr().out
    assert "love" in output
    assert "no pronunciations matched region Central-American" in output

    assert main(["--json", *cli_args(pronunciation_artifact, "--region", "Central-American")]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["entries"] == []
