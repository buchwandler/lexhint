from __future__ import annotations

import json
from pathlib import Path

import pytest

from lexhint import Lexicon, LexiconCapabilityError, PronunciationEntry
from lexhint.builder import build_dictionary


@pytest.fixture
def pronunciation_artifact(tmp_path: Path) -> Path:
    records = [
        {
            "word": "zeta",
            "lang_code": "en",
            "pos": "noun",
            "sounds": [{"ipa": "/z/"}],
            "senses": [{"glosses": ["z"]}],
        },
        {
            "word": "die",
            "lang_code": "en",
            "pos": "det",
            "sounds": [{"ipa": "[diː]"}],
            "senses": [{"glosses": ["the"]}],
        },
        {
            "word": "live",
            "lang_code": "en",
            "pos": "verb",
            "sounds": [{"ipa": "[ˈlɪv]"}],
            "senses": [{"glosses": ["alive"]}],
        },
        {
            "word": "Alpha",
            "lang_code": "en",
            "pos": "noun",
            "sounds": [{"ipa": "[a]"}],
            "senses": [{"glosses": ["first"]}],
        },
        {
            "word": "live",
            "lang_code": "en",
            "pos": "adjective",
            "sounds": [
                {"ipa": "/ˈlaɪ̯v/", "tags": ["General-American"]},
                {"ipa": "[ˈlaɪ̯v]", "tags": ["General-American"]},
                {"ipa": "[ˈlɪv]", "tags": ["Received-Pronunciation"]},
                {"ipa": "[ˈlɪv]"},
            ],
            "senses": [{"glosses": ["broadcast"]}],
        },
        {
            "word": "die",
            "lang_code": "en",
            "pos": "pronoun",
            "sounds": [{"ipa": "[diː]"}],
            "senses": [{"glosses": ["that"]}],
        },
        {
            "word": "Die",
            "lang_code": "en",
            "pos": "noun",
            "sounds": [{"ipa": "[daɪ]"}],
            "senses": [{"glosses": ["plural"]}],
        },
    ]
    source = tmp_path / "pronunciations.jsonl"
    source.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    artifact, _ = build_dictionary(
        "en",
        source,
        output=tmp_path / "pronunciations.sqlite3",
        capabilities="lexical,dictionary",
        no_frequency=True,
    )
    return artifact


def test_pronunciation_entry_is_public() -> None:
    entry = PronunciationEntry("word", ())
    assert entry.key == "word"
    assert entry.groups == ()


def test_bulk_lookup_matches_repeated_lookup(pronunciation_artifact: Path) -> None:
    lexicon = Lexicon.from_path(pronunciation_artifact)
    keys = ("alpha", "die", "live", "zeta")

    bulk = tuple(lexicon.iter_pronunciations(include_neutral=True))
    expected = tuple(
        PronunciationEntry(key, lexicon.pronunciations(key, include_neutral=True))
        for key in keys
        if lexicon.pronunciations(key, include_neutral=True)
    )

    assert bulk == expected
    assert tuple(entry.key for entry in bulk) == keys


def test_case_variants_are_grouped_under_one_key(pronunciation_artifact: Path) -> None:
    entry = next(Lexicon.from_path(pronunciation_artifact).iter_pronunciations())

    assert entry.key == "alpha"
    die = next(
        item
        for item in Lexicon.from_path(pronunciation_artifact).iter_pronunciations()
        if item.key == "die"
    )
    assert [(group.word, group.pos) for group in die.groups] == [
        ("die", "det"),
        ("die", "pronoun"),
        ("Die", "noun"),
    ]


def test_locale_and_neutral_filtering_match_lookup(pronunciation_artifact: Path) -> None:
    for locale in ("en_US", "en_GB"):
        lexicon = Lexicon.from_path(pronunciation_artifact, locale=locale)
        bulk = tuple(lexicon.iter_pronunciations(include_neutral=True))
        expected = tuple(
            PronunciationEntry(key, lexicon.pronunciations(key, include_neutral=True))
            for key in ("alpha", "die", "live", "zeta")
            if lexicon.pronunciations(key, include_neutral=True)
        )
        assert bulk == expected

    american = Lexicon.from_path(pronunciation_artifact, locale="en_US")
    live = next(item for item in american.iter_pronunciations() if item.key == "live")
    adjective = next(group for group in live.groups if group.pos == "adjective")
    assert tuple(item.ipa for item in adjective.pronunciations) == ("[ˈlaɪ̯v]",)

    british = Lexicon.from_path(pronunciation_artifact, locale="en_GB")
    live = next(item for item in british.iter_pronunciations() if item.key == "live")
    adjective = next(group for group in live.groups if group.pos == "adjective")
    assert tuple(item.ipa for item in adjective.pronunciations) == ("[ˈlɪv]",)


def test_neutral_false_and_pos_filter_skip_unmatched_groups(pronunciation_artifact: Path) -> None:
    lexicon = Lexicon.from_path(pronunciation_artifact, locale="en_US")
    live = next(item for item in lexicon.iter_pronunciations() if item.key == "live")
    adjective = next(group for group in live.groups if group.pos == "adjective")
    assert all(item.tags for item in adjective.pronunciations)

    nouns = tuple(lexicon.iter_pronunciations(include_pos=frozenset({"NOUN"})))
    assert tuple(item.key for item in nouns) == ("alpha", "die", "zeta")
    assert all(group.pos == "noun" for item in nouns for group in item.groups)


def test_iterator_is_lazy_and_uses_one_connection(
    pronunciation_artifact: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lexicon = Lexicon.from_path(pronunciation_artifact)
    calls = 0
    connect = lexicon._connect

    def counted_connect():
        nonlocal calls
        calls += 1
        return connect()

    monkeypatch.setattr(lexicon, "_connect", counted_connect)
    iterator = lexicon.iter_pronunciations()
    assert calls == 0
    assert next(iterator).key == "alpha"
    assert calls == 1
    assert tuple(item.key for item in iterator) == ("die", "live", "zeta")
    assert calls == 1


def test_iterator_requires_dictionary_capability(tmp_path: Path) -> None:
    source = tmp_path / "lexical.jsonl"
    source.write_text(
        json.dumps(
            {
                "word": "word",
                "lang_code": "en",
                "pos": "noun",
                "sounds": [{"ipa": "[wɜːd]"}],
                "senses": [{"glosses": ["term"]}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    artifact, _ = build_dictionary(
        "en",
        source,
        output=tmp_path / "lexical.sqlite3",
        capabilities="lexical",
        no_frequency=True,
    )

    with pytest.raises(LexiconCapabilityError, match="dictionary"):
        tuple(Lexicon.from_path(artifact).iter_pronunciations())
