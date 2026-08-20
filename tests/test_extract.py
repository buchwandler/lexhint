from lexhint.extract import dictionary_entries
from lexhint.models import DictionaryEntry, Example, Form, Pronunciation, Sense


def test_extracts_ipa_pronunciations_and_ignores_audio_only_rows() -> None:
    raw = {
        "word": "compiler",
        "lang_code": "en",
        "pos": "noun",
        "topics": ["computing"],
        "etymology_text": "From compile.",
        "forms": [{"form": "compilers", "tags": ["plural"]}],
        "sounds": [
            {"ipa": "/kəmˈpaɪlə/", "tags": ["UK"]},
            {"audio": "LL-Q1860 (eng)-Vealhurl-compiler.wav", "tags": ["Southern-England"]},
            {"ipa": "/kəmˈpaɪlɚ/", "tags": ["US"]},
            {"tags": ["audio-only"]},
            {"ipa": "/kəmˈpaɪlə/", "tags": ["UK"]},
        ],
        "senses": [
            {
                "glosses": ["A program that translates source code."],
                "tags": ["countable"],
                "examples": [{"text": "The compiler ran.", "translation": "Der Compiler lief."}],
                "synonyms": [{"word": "translator"}],
            }
        ],
    }

    assert tuple(dictionary_entries(raw, language="en")) == (
        DictionaryEntry(
            word="compiler",
            pos="noun",
            senses=(
                Sense(
                    glosses=("A program that translates source code.",),
                    topics=("computing",),
                    tags=("countable",),
                    examples=(Example("The compiler ran.", "Der Compiler lief."),),
                    synonyms=("translator",),
                ),
            ),
            forms=(Form("compilers", ("plural",)),),
            pronunciations=(
                Pronunciation("/kəmˈpaɪlə/", ("UK",)),
                Pronunciation("/kəmˈpaɪlɚ/", ("US",)),
            ),
            etymology="From compile.",
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
