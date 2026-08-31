from __future__ import annotations

import json
from pathlib import Path

import pytest

from lexhint import Lexicon, LexiconCapabilityError, PronunciationGroup
from lexhint.builder import build_dictionary


@pytest.fixture
def pronunciation_artifact(tmp_path: Path) -> Path:
    source = tmp_path / "pronunciations.jsonl"
    records = [
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
                {"ipa": "/australia/", "tags": ["Australia", "New-Zealand"]},
                {"ipa": "/neutral/", "tags": []},
                {"ipa": "/central/", "tags": ["Central-American"]},
                {"ipa": "/general/", "tags": ["General American"]},
            ],
            "senses": [{"glosses": ["affection"]}],
        },
        {
            "word": "love",
            "lang_code": "en",
            "pos": "noun",
            "sounds": [
                {"ipa": "/multi/", "tags": ["Canada", "General-American", "Received-Pronunciation"]}
            ],
            "senses": [{"glosses": ["another noun"]}],
        },
        {
            "word": "love",
            "lang_code": "en",
            "pos": "verb",
            "sounds": [
                {
                    "ipa": "/multi/",
                    "tags": ["Canada", "General-American", "Received-Pronunciation"],
                },
                {"ipa": "/neutral/", "tags": []},
            ],
            "senses": [{"glosses": ["to love"]}],
        },
        {
            "word": "love",
            "lang_code": "en",
            "pos": "adjective",
            "sounds": [{"ipa": "/adjective/", "tags": ["lovely"]}],
            "senses": [{"glosses": ["not selected"]}],
        },
    ]
    source.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    artifact, _ = build_dictionary(
        "en",
        source,
        output=tmp_path / "pronunciations.sqlite3",
        capabilities="lexical,dictionary",
        no_frequency=True,
    )
    return artifact


def test_unfiltered_groups_and_deduplicates_per_pos(pronunciation_artifact: Path) -> None:
    values = Lexicon.from_path(pronunciation_artifact).pronunciations("love")

    assert all(isinstance(value, PronunciationGroup) for value in values)
    assert [value.pos for value in values] == ["noun", "verb", "adjective"]
    assert [value.ipa for value in values[0].pronunciations] == [
        "/multi/",
        "/australia/",
        "/neutral/",
        "/central/",
        "/general/",
    ]
    assert [value.ipa for value in values[1].pronunciations] == ["/multi/", "/neutral/"]


def test_region_matching_is_exact_normalized_and_supports_multi_tags(
    pronunciation_artifact: Path,
) -> None:
    lexicon = Lexicon.from_path(pronunciation_artifact)

    assert [
        value.ipa for value in lexicon.pronunciations("love", region="cAnAdA")[0].pronunciations
    ] == ["/multi/"]
    assert [
        value.ipa
        for value in lexicon.pronunciations("love", region="General_American")[0].pronunciations
    ] == [
        "/multi/",
        "/general/",
    ]
    assert [
        value.ipa
        for value in lexicon.pronunciations("love", region="Central-American")[0].pronunciations
    ] == ["/central/"]
    assert lexicon.pronunciations("love", region="America") == ()
    assert lexicon.pronunciations("love", region="Australian") == ()


def test_locale_matching_uses_profiles_and_tag_intersection(pronunciation_artifact: Path) -> None:
    for locale in ("en_US", "en_GB", "en_CA"):
        values = Lexicon.from_path(pronunciation_artifact, locale=locale).pronunciations("love")
        assert values[0].pronunciations[0].ipa == "/multi/"
    assert (
        Lexicon.from_path(pronunciation_artifact, locale="en_US")
        .pronunciations("love")[0]
        .pronunciations[-1]
        .ipa
        == "/general/"
    )
    assert (
        Lexicon.from_path(pronunciation_artifact, locale="en_US")
        .pronunciations("love")[0]
        .pronunciations[-1]
        .ipa
        != "/australia/"
    )


def test_neutral_and_pos_filtering(pronunciation_artifact: Path) -> None:
    lexicon = Lexicon.from_path(pronunciation_artifact)
    assert [
        value.ipa for value in lexicon.pronunciations("love", region="Canada")[0].pronunciations
    ] == ["/multi/"]
    assert [
        value.ipa
        for value in lexicon.pronunciations("love", region="Canada", include_neutral=True)[
            0
        ].pronunciations
    ] == [
        "/multi/",
        "/neutral/",
    ]
    assert [
        value.pos for value in lexicon.pronunciations("love", include_pos=frozenset({"NOUN"}))
    ] == ["noun"]
    assert lexicon.pronunciations("love", region="Canada", include_pos=frozenset({"missing"})) == ()


def test_validation_and_capability(pronunciation_artifact: Path, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="region cannot be combined"):
        Lexicon.from_path(pronunciation_artifact, locale="en_US").pronunciations(
            "love", region="Canada"
        )

    lexical_source = tmp_path / "lexical-source.jsonl"
    lexical_source.write_text(
        '{"word":"love","lang_code":"en","pos":"noun","sounds":[],"senses":[{"glosses":["love"]}]}\n',
        encoding="utf-8",
    )
    lexical, _ = build_dictionary(
        "en",
        lexical_source,
        output=tmp_path / "lexical.sqlite3",
        capabilities="lexical",
        no_frequency=True,
    )
    with pytest.raises(LexiconCapabilityError, match="dictionary"):
        Lexicon.from_path(lexical).pronunciations("love")


def test_empty_result_and_unknown_word(pronunciation_artifact: Path) -> None:
    lexicon = Lexicon.from_path(pronunciation_artifact)
    assert lexicon.pronunciations("love", region="Central-America") == ()
    assert lexicon.pronunciations("missing") == ()
