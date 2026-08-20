from lexhint.extract import dictionary_entries
from lexhint.models import DictionaryEntry, Example, Form, Pronunciation, Sense


def test_extracts_curated_rich_entry_in_source_order() -> None:
    raw = {
        "word": "love",
        "lang_code": "en",
        "pos": "noun",
        "topics": ["emotion"],
        "etymology_text": "From Middle English.",
        "forms": [{"form": "loves", "tags": ["plural"]}],
        "sounds": [{"ipa": "/lʌv/", "audio": "Love.ogg", "tags": ["US"]}],
        "senses": [
            {
                "glosses": ["A strong feeling of affection."],
                "tags": ["uncountable"],
                "examples": [{"text": "Their love grew.", "translation": "Liebe."}],
                "synonyms": [{"word": "affection"}],
                "antonyms": [{"word": "hate"}],
            },
            {"glosses": ["Zero score in tennis."], "topics": ["sports"]},
        ],
        "categories": ["maintenance noise"],
    }

    entries = tuple(dictionary_entries(raw, language="en"))

    assert entries == (
        DictionaryEntry(
            word="love",
            pos="noun",
            senses=(
                Sense(
                    glosses=("A strong feeling of affection.",),
                    topics=("emotion",),
                    tags=("uncountable",),
                    examples=(Example("Their love grew.", "Liebe."),),
                    synonyms=("affection",),
                    antonyms=("hate",),
                ),
                Sense(glosses=("Zero score in tennis.",), topics=("emotion", "sports")),
            ),
            forms=(Form("loves", ("plural",)),),
            pronunciations=(Pronunciation("/lʌv/", "Love.ogg", ("US",)),),
            etymology="From Middle English.",
        ),
    )


def test_extracts_missing_optional_fields_and_filters_language() -> None:
    raw = {
        "word": "House",
        "lang_code": "de",
        "pos": "noun",
        "senses": [{"glosses": ["wrong language"]}],
    }
    assert tuple(dictionary_entries(raw, language="en")) == ()
    assert (
        tuple(
            dictionary_entries(
                {"word": "word", "lang_code": "en", "senses": [{"glosses": ["definition"]}]},
                language="en",
            )
        )[0].forms
        == ()
    )
