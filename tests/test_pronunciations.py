from __future__ import annotations

import json
from pathlib import Path

import pytest

from lexhint import Lexicon, LexiconCapabilityError, PronunciationGroup
from lexhint.builder import build_dictionary
from lexhint.pronunciation import format_ipa, normalize_ipa_body


def test_ipa_normalization_and_formatting() -> None:
    assert normalize_ipa_body("/ˈlʌv/") == "ˈlʌv"
    assert normalize_ipa_body("[ˈlʌv]") == "ˈlʌv"
    assert normalize_ipa_body(" /ˈlʌv/ ") == "ˈlʌv"
    assert normalize_ipa_body("/[x/y]/") == "[x/y]"
    assert normalize_ipa_body("[x/y]") == "x/y"
    assert normalize_ipa_body("") == ""
    assert format_ipa("/ˈlʌv/") == "[ˈlʌv]"
    assert format_ipa("[ˈlʌv]") == "[ˈlʌv]"
    assert format_ipa(" ") == ""


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
                {
                    "ipa": "[multi]",
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
        {
            "word": "foo",
            "lang_code": "de",
            "pos": "noun",
            "sounds": [{"ipa": "[a]"}],
            "senses": [{"glosses": ["a"]}],
        },
        {
            "word": "Foo",
            "lang_code": "de",
            "pos": "noun",
            "sounds": [{"ipa": "[b]"}],
            "senses": [{"glosses": ["b"]}],
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


def test_unfiltered_groups_and_deduplicates_per_pos(pronunciation_artifact: Path) -> None:
    values = Lexicon.from_path(pronunciation_artifact).pronunciations("love")

    assert all(isinstance(value, PronunciationGroup) for value in values)
    assert [value.pos for value in values] == ["noun", "verb", "adjective"]
    assert [value.ipa for value in values[0].pronunciations] == [
        "[multi]",
        "[australia]",
        "[neutral]",
        "[central]",
        "[general]",
    ]
    assert [value.ipa for value in values[1].pronunciations] == ["[multi]", "[neutral]"]


def test_delimiter_equivalence_and_distinct_identity(pronunciation_artifact: Path) -> None:
    lexicon = Lexicon.from_path(pronunciation_artifact)
    values = lexicon.pronunciations("love")
    assert values[0].word == "love"
    assert [value.ipa for value in values[0].pronunciations] == [
        "[multi]",
        "[australia]",
        "[neutral]",
        "[central]",
        "[general]",
    ]
    assert values[0].pronunciations[0].tags == (
        "Canada",
        "General-American",
        "Received-Pronunciation",
    )
    assert values[0].pronunciations[1].tags == ("Australia", "New-Zealand")
    assert values[0].pronunciations[2].tags == ()


def test_region_matching_is_exact_normalized_and_supports_multi_tags(
    pronunciation_artifact: Path,
) -> None:
    lexicon = Lexicon.from_path(pronunciation_artifact)

    assert [
        value.ipa for value in lexicon.pronunciations("love", region="cAnAdA")[0].pronunciations
    ] == ["[multi]"]
    assert [
        value.ipa
        for value in lexicon.pronunciations("love", region="General_American")[0].pronunciations
    ] == [
        "[multi]",
        "[general]",
    ]
    assert [
        value.ipa
        for value in lexicon.pronunciations("love", region="Central-American")[0].pronunciations
    ] == ["[central]"]
    assert lexicon.pronunciations("love", region="America") == ()
    assert lexicon.pronunciations("love", region="Australian") == ()


def test_locale_matching_uses_profiles_and_tag_intersection(pronunciation_artifact: Path) -> None:
    for locale in ("en_US", "en_GB", "en_CA"):
        values = Lexicon.from_path(pronunciation_artifact, locale=locale).pronunciations("love")
        assert values[0].pronunciations[0].ipa == "[multi]"
    assert (
        Lexicon.from_path(pronunciation_artifact, locale="en_US")
        .pronunciations("love")[0]
        .pronunciations[-1]
        .ipa
        == "[general]"
    )
    assert (
        Lexicon.from_path(pronunciation_artifact, locale="en_US")
        .pronunciations("love")[0]
        .pronunciations[-1]
        .ipa
        != "[australia]"
    )


def test_locale_falls_back_to_untagged_pronunciation_per_group(
    locale_fallback_artifact: Path,
) -> None:
    values = Lexicon.from_path(
        locale_fallback_artifact,
        locale="en_US",
    ).pronunciations("live")

    assert [
        (
            value.pos,
            tuple(pronunciation.ipa for pronunciation in value.pronunciations),
        )
        for value in values
    ] == [
        ("verb", ("[ˈlɪv]",)),
        ("adj", ("[ˈlaɪ̯v]",)),
        ("adv", ("[ˈlaɪ̯v]",)),
    ]
    assert all(not pronunciation.tags for value in values for pronunciation in value.pronunciations)


def test_locale_specific_match_prevents_implicit_neutral_fallback(
    pronunciation_artifact: Path,
) -> None:
    values = Lexicon.from_path(
        pronunciation_artifact,
        locale="en_US",
    ).pronunciations("love")

    noun = next(value for value in values if value.pos == "noun")
    assert "[neutral]" not in {pronunciation.ipa for pronunciation in noun.pronunciations}
    assert "adjective" not in {value.pos for value in values}


def test_locale_include_neutral_adds_neutral_alongside_matches(
    pronunciation_artifact: Path,
) -> None:
    values = Lexicon.from_path(
        pronunciation_artifact,
        locale="en_US",
    ).pronunciations("love", include_neutral=True)

    noun = next(value for value in values if value.pos == "noun")
    assert [pronunciation.ipa for pronunciation in noun.pronunciations] == [
        "[multi]",
        "[general]",
        "[neutral]",
    ]


def test_locale_without_match_or_neutral_omits_group(
    pronunciation_artifact: Path,
) -> None:
    values = Lexicon.from_path(
        pronunciation_artifact,
        locale="en_US",
    ).pronunciations("love", include_pos=frozenset({"adjective"}))

    assert values == ()


def test_neutral_and_pos_filtering(pronunciation_artifact: Path) -> None:
    lexicon = Lexicon.from_path(pronunciation_artifact)
    assert [
        value.ipa for value in lexicon.pronunciations("love", region="Canada")[0].pronunciations
    ] == ["[multi]"]
    assert [
        value.ipa
        for value in lexicon.pronunciations("love", region="Canada", include_neutral=True)[
            0
        ].pronunciations
    ] == [
        "[multi]",
        "[neutral]",
    ]
    assert [
        value.pos for value in lexicon.pronunciations("love", include_pos=frozenset({"NOUN"}))
    ] == ["noun"]
    assert lexicon.pronunciations("love", region="Canada", include_pos=frozenset({"missing"})) == ()


def test_case_variants_are_returned_in_query_order(case_variant_artifact: Path) -> None:
    lexicon = Lexicon.from_path(case_variant_artifact)
    lowercase = lexicon.pronunciations("die")
    titlecase = lexicon.pronunciations("Die")
    assert {group.word for group in lowercase} == {"die", "Die"}
    assert {group.word for group in titlecase} == {"die", "Die"}
    assert lowercase[0].word == "die"
    assert titlecase[0].word == "Die"
    assert tuple(entry.word for entry in lexicon.entries("die")) == ("die", "die")
    assert tuple(entry.word for entry in lexicon.entries("die", all_case_variants=True)) == (
        "die",
        "die",
        "Die",
    )
    assert [(group.word, group.pos) for group in lowercase] == [
        ("die", "det"),
        ("die", "pron"),
        ("Die", "noun"),
    ]
    assert [(group.word, group.pos) for group in titlecase] == [
        ("Die", "noun"),
        ("die", "det"),
        ("die", "pron"),
    ]
    assert {
        group.pos for group in lexicon.pronunciations("die", include_pos=frozenset({"noun"}))
    } == {"noun"}
    assert [
        (group.word, group.pos, tuple(item.ipa for item in group.pronunciations))
        for group in lexicon.pronunciations("foo")
    ] == [
        ("foo", "noun", ("[a]",)),
        ("Foo", "noun", ("[b]",)),
    ]


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
