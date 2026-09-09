from lexhint.extract import dictionary_entries
from lexhint.models import (
    DictionaryEntry,
    Example,
    ExtractionDiagnostics,
    Form,
    Pronunciation,
    Sense,
)


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


def test_preserves_raw_pronunciation_tags_and_filters_x_sampa() -> None:
    diagnostics = ExtractionDiagnostics()
    raw = {
        "word": "leite",
        "lang_code": "pt",
        "pos": "noun",
        "sounds": [
            {"ipa": "/ˈlej.te/", "raw_tags": ["Caipira"]},
            {"ipa": '/"lej.tSe/', "raw_tags": ["Caipira"]},
            {"ipa": "/ˈlej.tʃi/", "raw_tags": ["Paulistana"]},
            {"ipa": '/"lej.tSi/', "raw_tags": ["Paulistana"]},
        ],
        "senses": [{"glosses": ["milk"]}],
    }

    entry = next(dictionary_entries(raw, language="pt", diagnostics=diagnostics))
    assert entry.pronunciations == (
        Pronunciation("/ˈlej.te/", ("Caipira",)),
        Pronunciation("/ˈlej.tʃi/", ("Paulistana",)),
    )
    assert diagnostics.pronunciation_invalid_ipa == 2


def test_normalized_pronunciation_tags_take_precedence_over_raw_tags() -> None:
    raw = {
        "word": "leite",
        "lang_code": "pt",
        "pos": "noun",
        "sounds": [{"ipa": "/ˈlej.te/", "tags": ["Brazil"], "raw_tags": ["Caipira"]}],
        "senses": [{"glosses": ["milk"]}],
    }

    entry = next(dictionary_entries(raw, language="pt"))
    assert entry.pronunciations == (Pronunciation("/ˈlej.te/", ("Brazil",)),)
