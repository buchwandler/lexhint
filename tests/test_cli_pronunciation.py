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


@pytest.fixture
def portuguese_artifact(tmp_path: Path) -> Path:
    source = tmp_path / "portuguese.jsonl"
    source.write_text(
        json.dumps(
            {
                "word": "leite",
                "lang_code": "pt",
                "pos": "noun",
                "sounds": [
                    {"ipa": "/ˈlej.te/", "tags": ["Caipira"]},
                    {"ipa": "/ˈlɐj.tɨ/", "tags": ["Portugal"]},
                ],
                "senses": [{"glosses": ["milk"]}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    artifact, _ = build_dictionary(
        "pt",
        source,
        output=tmp_path / "pt.sqlite3",
        capabilities="lexical,dictionary",
        no_frequency=True,
    )
    return artifact


@pytest.fixture
def locale_fallback_artifact(tmp_path: Path) -> Path:
    source = tmp_path / "locale-fallback.jsonl"
    records = [
        {
            "word": "live",
            "lang_code": "en",
            "pos": "verb",
            "sounds": [{"ipa": "[ˈlɪv]"}],
            "senses": [{"glosses": ["to be alive"]}],
        },
        {
            "word": "live",
            "lang_code": "en",
            "pos": "adj",
            "sounds": [
                {"ipa": "[ˈlaɪ̯v]"},
                {
                    "ipa": "[ˈlaːv]",
                    "tags": ["General-South-African", "Southern-US"],
                },
            ],
            "senses": [{"glosses": ["alive"]}],
        },
        {
            "word": "live",
            "lang_code": "en",
            "pos": "adv",
            "sounds": [
                {"ipa": "[ˈlaɪ̯v]"},
                {
                    "ipa": "[ˈlaːv]",
                    "tags": ["General-South-African", "Southern-US"],
                },
            ],
            "senses": [{"glosses": ["in a live manner"]}],
        },
    ]
    source.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    artifact, _ = build_dictionary(
        "en",
        source,
        output=tmp_path / "locale-fallback.sqlite3",
        capabilities="lexical,dictionary",
        no_frequency=True,
    )
    return artifact


@pytest.fixture
def case_variant_artifact(tmp_path: Path) -> Path:
    source = tmp_path / "case-variants.jsonl"
    records = [
        {
            "word": "die",
            "lang_code": "de",
            "pos": "det",
            "sounds": [{"ipa": "[diː]"}],
            "senses": [{"glosses": ["the"]}],
        },
        {
            "word": "die",
            "lang_code": "de",
            "pos": "pron",
            "sounds": [{"ipa": "[diː]"}],
            "senses": [{"glosses": ["that"]}],
        },
        {
            "word": "Die",
            "lang_code": "de",
            "pos": "noun",
            "sounds": [{"ipa": "[daɪ]"}],
            "senses": [{"glosses": ["plural"]}],
        },
    ]
    source.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    artifact, _ = build_dictionary(
        "de",
        source,
        output=tmp_path / "case-variants.sqlite3",
        capabilities="lexical,dictionary",
        no_frequency=True,
    )
    return artifact


def cli_args(path: Path, *extra: str) -> list[str]:
    return ["dictionary", "pronunciation", "love", "--path", str(path), *extra]


def case_cli_args(path: Path, word: str, *extra: str) -> list[str]:
    return ["dictionary", "pronunciation", word, "-l", "de", "--path", str(path), *extra]


def test_cli_locale_uses_neutral_fallback_when_no_specific_match(
    locale_fallback_artifact: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        main(
            [
                "dictionary",
                "pronunciation",
                "live",
                "--path",
                str(locale_fallback_artifact),
                "--locale",
                "en_US",
            ]
        )
        == 0
    )

    assert capsys.readouterr().out.splitlines() == [
        "live",
        "  verb",
        "    [ˈlɪv]",
        "  adj",
        "    [ˈlaɪ̯v]",
        "  adv",
        "    [ˈlaɪ̯v]",
    ]


def test_cli_json_locale_uses_the_same_fallback_selection(
    locale_fallback_artifact: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        main(
            [
                "--json",
                "dictionary",
                "pronunciation",
                "live",
                "--path",
                str(locale_fallback_artifact),
                "--locale",
                "en_US",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["language"] == "en"
    assert payload["locale"] == "US"
    assert payload["region"] is None
    assert payload["include_neutral"] is False
    assert [(entry["pos"], entry["pronunciations"]) for entry in payload["entries"]] == [
        ("verb", [{"ipa": "[ˈlɪv]", "tags": []}]),
        ("adj", [{"ipa": "[ˈlaɪ̯v]", "tags": []}]),
        ("adv", [{"ipa": "[ˈlaɪ̯v]", "tags": []}]),
    ]


def test_cli_locale_preserves_no_match_message(
    pronunciation_artifact: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(cli_args(pronunciation_artifact, "--locale", "en_US", "--pos", "adjective")) == 0
    assert "no pronunciations matched locale US" in capsys.readouterr().out


def test_human_pronunciation_output_is_grouped_and_focused(
    pronunciation_artifact: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(cli_args(pronunciation_artifact, "--region", "Canada")) == 0

    output = capsys.readouterr().out
    assert output.splitlines() == [
        "love",
        "  noun",
        "    [multi] [Canada, General-American, Received-Pronunciation]",
        "  verb",
        "    [multi] [Canada, General-American, Received-Pronunciation]",
    ]
    assert "not shown" not in output


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        (
            "die",
            [
                "die",
                "  det",
                "    [diː]",
                "  pron",
                "    [diː]",
                "Die",
                "  noun",
                "    [daɪ]",
            ],
        ),
        (
            "Die",
            [
                "Die",
                "  noun",
                "    [daɪ]",
                "die",
                "  det",
                "    [diː]",
                "  pron",
                "    [diː]",
            ],
        ),
    ],
)
def test_cli_renders_case_variants(
    case_variant_artifact: Path,
    capsys: pytest.CaptureFixture[str],
    word: str,
    expected: list[str],
) -> None:
    assert main(case_cli_args(case_variant_artifact, word)) == 0
    assert capsys.readouterr().out.splitlines() == expected


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
            "ipa": "[multi]",
            "tags": ["Canada", "General-American", "Received-Pronunciation"],
        }
    ]
    assert "\x1b[" not in capsys.readouterr().out


def test_cli_json_exposes_case_variant_words(
    case_variant_artifact: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--json", *case_cli_args(case_variant_artifact, "die")]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert [(entry["word"], entry["pos"]) for entry in payload["entries"]] == [
        ("die", "det"),
        ("die", "pron"),
        ("Die", "noun"),
    ]
    assert [entry["pronunciations"][0]["ipa"] for entry in payload["entries"]] == [
        "[diː]",
        "[diː]",
        "[daɪ]",
    ]
    assert "\x1b[" not in json.dumps(payload)


def test_cli_pos_and_neutral_validation(
    pronunciation_artifact: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(cli_args(pronunciation_artifact, "--region", "Canada", "--pos", "noun")) == 0
    assert "  verb" not in capsys.readouterr().out

    assert main(cli_args(pronunciation_artifact, "--include-neutral")) == 0
    output = capsys.readouterr().out
    assert "[neutral]" in output


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


def test_cli_full_locale_infers_portuguese_and_adds_canonical_tag(
    portuguese_artifact: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(
            [
                "--json",
                "dictionary",
                "pronunciation",
                "leite",
                "--path",
                str(portuguese_artifact),
                "--locale",
                "pt_pt",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["language"] == "pt"
    assert payload["locale"] == "PT"
    assert payload["locale_tag"] == "pt-PT"
    assert payload["entries"][0]["pronunciations"] == [{"ipa": "[ˈlɐj.tɨ]", "tags": ["Portugal"]}]


def test_cli_rejects_locale_language_mismatch(
    portuguese_artifact: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = main(
        [
            "dictionary",
            "pronunciation",
            "leite",
            "-l",
            "en",
            "--path",
            str(portuguese_artifact),
            "--locale",
            "pt-BR",
        ]
    )
    assert result == 1
    assert "locale 'pt-BR' selects language 'pt' but --language is 'en'" in capsys.readouterr().err


def test_cli_rejects_short_locale_without_language(
    pronunciation_artifact: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(cli_args(pronunciation_artifact, "--locale", "BR")) == 1
    captured = capsys.readouterr()
    assert "locale 'BR' does not identify a language" in captured.err
    assert "--language" in captured.err


def test_cli_accepts_short_locale_with_explicit_or_positional_language(
    portuguese_artifact: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for values in (("leite", "-l", "pt"), ("pt", "leite")):
        assert main(
            [
                "dictionary",
                "pronunciation",
                *values,
                "--path",
                str(portuguese_artifact),
                "--locale",
                "BR",
            ]
        ) == 0
        assert "[ˈlej.te] [Caipira]" in capsys.readouterr().out


def test_cli_dictionary_word_infers_language_from_locale(
    portuguese_artifact: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(
            [
                "--json",
                "dictionary",
                "word",
                "leite",
                "--path",
                str(portuguese_artifact),
                "--locale",
                "pt-BR",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["language"] == "pt"
    assert payload["locale_tag"] == "pt-BR"


def test_cli_rejects_undocumented_long_option_abbreviation(
    pronunciation_artifact: Path,
) -> None:
    with pytest.raises(SystemExit, match="2"):
        main(cli_args(pronunciation_artifact, "--local", "en-US"))


def test_cli_identifies_ambiguous_neutral_fallback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "ambiguous.jsonl"
    source.write_text(
        json.dumps(
            {
                "word": "leite",
                "lang_code": "pt",
                "pos": "noun",
                "sounds": [{"ipa": "/one/"}, {"ipa": "/two/"}],
                "senses": [{"glosses": ["milk"]}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    artifact, _ = build_dictionary(
        "pt",
        source,
        output=tmp_path / "ambiguous.sqlite3",
        capabilities="lexical,dictionary",
        no_frequency=True,
    )
    assert (
        main(
            [
                "dictionary",
                "pronunciation",
                "leite",
                "--path",
                str(artifact),
                "--locale",
                "pt-BR",
            ]
        )
        == 0
    )
    assert "no pt-BR-tagged pronunciation is available" in capsys.readouterr().out
