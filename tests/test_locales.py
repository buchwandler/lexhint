from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from lexhint import Lexicon
from lexhint.builder import build_dictionary
from lexhint.languages import (
    normalize_language,
    normalize_locale,
    normalize_source_region_tag,
    source_tags_match_locale,
    source_tags_match_region,
    supported_base_languages,
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
        "cs",
        "de",
        "en",
        "es",
        "fr",
        "it",
        "ja",
        "ko",
        "pt",
        "ru",
        "th",
        "vi",
        "zh",
    )
    with pytest.raises(ValueError, match="unsupported locale 'AU'"):
        normalize_locale("en", "AU")
    with pytest.raises(ValueError, match="not supported for language 'de'"):
        normalize_locale("de", "GB")


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
        "en",
        "es",
        "fr",
        "it",
        "ja",
        "ko",
        "pt",
        "ru",
        "th",
        "vi",
        "zh",
    ),
)
def test_every_supported_base_language_normalizes(language: str) -> None:
    assert normalize_language(language) == language


@pytest.mark.parametrize(
    ("language", "word"),
    [
        ("ja", "家"),
        ("ko", "집"),
        ("ru", "дом"),
        ("th", "บ้าน"),
        ("vi", "nhà"),
        ("zh", "家"),
    ],
)
def test_new_base_languages_build_tiny_lexical_artifact(
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
