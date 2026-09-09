from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from lexhint import Lexicon
from lexhint.builder import build_dictionary
from lexhint.languages import (
    locale_language,
    locale_tag,
    normalize_language,
    normalize_locale,
    normalize_source_region_tag,
    source_tags_match_locale,
    source_tags_match_region,
    supported_base_languages,
    supported_locale_specs,
    supported_locale_tags,
)
from lexhint.models import DictionaryEntry, Form, Pronunciation, Sense
from lexhint.render import (
    DictionaryRenderOptions,
    render_dictionary_entries,
    resolve_dictionary_fields,
)


def test_locale_normalization_and_base_language_contract() -> None:
    assert normalize_locale("en", None) is None
    assert normalize_locale("en", "GB") == "GB"
    assert normalize_locale("en", "en-GB") == "GB"
    assert normalize_locale("en", "en_GB") == "GB"
    assert normalize_locale("en", "US") == "US"
    assert normalize_locale("en", "en-US") == "US"
    assert normalize_locale("en", "en_CA") == "CA"
    assert normalize_locale("en", "en-CA") == "CA"
    assert normalize_locale("en", "CA") == "CA"
    assert normalize_source_region_tag("general_american") == "general-american"
    assert source_tags_match_region(("General American",), "GENERAL-AMERICAN")
    assert source_tags_match_locale(("Received-Pronunciation",), "en", "en_GB")
    assert not source_tags_match_region(("American",), "America")
    assert supported_base_languages() == (
        "ar",
        "az",
        "bg",
        "ca",
        "ceb",
        "cs",
        "de",
        "el",
        "en",
        "es",
        "fr",
        "ga",
        "he",
        "hi",
        "hu",
        "hy",
        "id",
        "it",
        "ja",
        "ko",
        "ku",
        "la",
        "lt",
        "lv",
        "mr",
        "ms",
        "nl",
        "pl",
        "pt",
        "ro",
        "ru",
        "sv",
        "ta",
        "te",
        "th",
        "tl",
        "tr",
        "uk",
        "ur",
        "vi",
        "zh",
    )
    with pytest.raises(ValueError, match="unsupported locale 'AU'"):
        normalize_locale("en", "AU")
    with pytest.raises(ValueError, match="not supported for language 'de'"):
        normalize_locale("de", "GB")


def test_portuguese_locale_profiles_and_full_tags() -> None:
    brazil_aliases = ("BR", "pt-BR", "pt_BR", "pt_br", "PT-br")
    assert [normalize_locale("pt", value) for value in brazil_aliases] == [
        "BR",
        "BR",
        "BR",
        "BR",
        "BR",
    ]
    assert [normalize_locale("pt", value) for value in ("PT", "pt-PT", "pt_PT", "pt_pt")] == [
        "PT",
        "PT",
        "PT",
        "PT",
    ]
    assert locale_language("pt-BR") == "pt"
    assert locale_language("pt_BR") == "pt"
    assert locale_language("BR") is None
    assert locale_language("pt-AO") == "pt"
    assert locale_tag("pt", "BR") == "pt-BR"
    assert supported_locale_tags("pt") == ("pt-BR", "pt-PT")
    assert tuple(spec.tag for spec in supported_locale_specs("pt")) == ("pt-BR", "pt-PT")


def test_portuguese_locale_source_tag_matching() -> None:
    assert source_tags_match_locale(("Brazil",), "pt", "pt-BR")
    assert source_tags_match_locale(("Northeast-Brazil",), "pt", "pt-BR")
    assert source_tags_match_locale(("Caipira",), "pt", "pt-BR")
    assert source_tags_match_locale(("Paulistana",), "pt", "pt-BR")
    assert source_tags_match_locale(("Portugal",), "pt", "pt-PT")
    assert source_tags_match_locale(("Northern", "Portugal"), "pt", "pt-PT")
    assert not source_tags_match_locale(("Brazil",), "pt", "pt-PT")
    assert not source_tags_match_locale(("Portugal",), "pt", "pt-BR")


@pytest.mark.parametrize(
    "language",
    (
        "ca",
        "sv",
        "lv",
        "lt",
        "nl",
        "ro",
        "hu",
        "bg",
        "uk",
        "ga",
        "la",
        "ar",
        "hy",
        "az",
        "ceb",
        "he",
        "hi",
        "mr",
        "tl",
        "ta",
        "te",
        "ur",
    ),
)
def test_expanded_languages_are_normalized(language: str) -> None:
    assert normalize_language(language) == language


@pytest.mark.parametrize("language", ["xx", "abcd"])
def test_unknown_language_codes_are_rejected(language: str) -> None:
    with pytest.raises(ValueError, match="unsupported Lexhint language"):
        normalize_language(language)


def test_locale_orders_retained_source_tags_and_keeps_neutral_order(tmp_path: Path) -> None:
    source = tmp_path / "locale.jsonl"
    source.write_text(
        json.dumps(
            {
                "word": "colour",
                "lang_code": "en",
                "pos": "noun",
                "forms": [
                    {"form": "color", "tags": ["US"]},
                    {"form": "colour", "tags": ["UK"]},
                    {"form": "colouring", "tags": []},
                ],
                "sounds": [
                    {"ipa": "/US/", "tags": ["US"]},
                    {"ipa": "/UK/", "tags": ["UK"]},
                    {"ipa": "/general/", "tags": []},
                ],
                "senses": [
                    {"glosses": ["American sense"], "tags": ["US"]},
                    {"glosses": ["British sense"], "tags": ["UK"]},
                    {"glosses": ["General sense"], "tags": []},
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    database, _ = build_dictionary(
        "en",
        source,
        output=tmp_path / "locale.sqlite3",
        capabilities="lexical,dictionary",
        no_frequency=True,
    )

    neutral = Lexicon("en", path=database)
    british = Lexicon("en", locale="en-GB", path=database)
    american = Lexicon("en", locale="US", path=database)
    assert neutral.path == british.path == american.path
    assert neutral.locale is None
    assert british.locale == "GB"
    assert american.locale == "US"
    assert [value.form for value in neutral.entries("colour")[0].forms] == [
        "color",
        "colour",
        "colouring",
    ]
    assert [value.form for value in british.entries("colour")[0].forms] == [
        "colour",
        "colouring",
        "color",
    ]
    assert [value.form for value in american.entries("colour")[0].forms] == [
        "color",
        "colouring",
        "colour",
    ]
    rendered = render_dictionary_entries(
        "colour",
        british.entries("colour"),
        options=DictionaryRenderOptions(
            fields=resolve_dictionary_fields("full"), locale="GB", width=100
        ),
    )
    assert "American English: color" in rendered


def test_incompatible_database_metadata_is_rejected_before_queries(tmp_path: Path) -> None:
    source = tmp_path / "minimal.jsonl"
    source.write_text(
        '{"word":"word","lang_code":"en","pos":"noun","senses":[{"glosses":["term"]}]}\n',
        encoding="utf-8",
    )
    database, _ = build_dictionary(
        "en",
        source,
        output=tmp_path / "incompatible.sqlite3",
        capabilities="lexical",
        no_frequency=True,
    )
    with closing(sqlite3.connect(database)) as connection:
        connection.execute("UPDATE metadata SET value='7' WHERE key='schema_version'")
        connection.commit()
    with pytest.raises(RuntimeError, match="uses schema 7"):
        Lexicon.from_path(database)


def test_model_tags_are_preserved() -> None:
    entry = DictionaryEntry(
        "word",
        "noun",
        (Sense(tags=("UK",)),),
        forms=(Form("word", ("US",)),),
        pronunciations=(Pronunciation("/word/", ("UK",)),),
    )
    assert entry.forms[0].tags == ("US",)
    assert entry.pronunciations[0].tags == ("UK",)


@pytest.mark.parametrize(
    "language",
    (
        "cs",
        "de",
        "el",
        "en",
        "es",
        "fr",
        "id",
        "it",
        "ja",
        "ko",
        "ku",
        "ms",
        "pl",
        "pt",
        "ru",
        "th",
        "tr",
        "vi",
        "zh",
    ),
)
def test_every_supported_base_language_normalizes(language: str) -> None:
    assert normalize_language(language) == language


@pytest.mark.parametrize(
    ("language", "word"),
    [
        ("cs", "čas"),
        ("de", "haus"),
        ("el", "σπίτι"),
        ("en", "house"),
        ("es", "casa"),
        ("fr", "maison"),
        ("id", "rumah"),
        ("it", "casa"),
        ("ja", "家"),
        ("ko", "집"),
        ("ku", "mal"),
        ("ms", "rumah"),
        ("pl", "dom"),
        ("pt", "casa"),
        ("ru", "дом"),
        ("th", "บ้าน"),
        ("tr", "ev"),
        ("vi", "nhà"),
        ("zh", "家"),
    ],
)
def test_supported_base_languages_build_tiny_lexical_artifact(
    language: str, word: str, tmp_path: Path
) -> None:
    assert normalize_language(language) == language
    source = tmp_path / f"{language}.jsonl"
    source.write_text(
        json.dumps(
            {
                "word": word,
                "lang_code": language,
                "pos": "noun",
                "senses": [{"glosses": ["fixture"]}],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    database, stats = build_dictionary(
        language,
        source,
        output=tmp_path / f"{language}.sqlite3",
        capabilities="lexical",
        no_frequency=True,
    )
    assert database.is_file()
    assert stats.words >= 1
