from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from lexhint import DictionaryEntry, Lexicon, LexiconCapabilityError, PronunciationEntry
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

    with pytest.raises(LexiconCapabilityError, match="dictionary"):
        tuple(Lexicon.from_path(artifact).iter_entries())


@pytest.fixture
def entry_stream_artifact(tmp_path: Path) -> Path:
    records = [
        {
            "word": "bank",
            "lang_code": "en",
            "pos": "noun",
            "etymology_number": 1,
            "topics": ["finance"],
            "sounds": [{"ipa": "[ˈlɪv]", "tags": ["General-American"]}],
            "senses": [
                {
                    "glosses": ["a financial institution"],
                    "topics": ["investment"],
                    "tags": ["countable"],
                    "examples": [
                        {
                            "text": "She went to the bank.",
                            "translation": "Elle est allée à la banque.",
                            "type": "quotation",
                        }
                    ],
                    "synonyms": [{"word": "depository", "tags": ["rare"]}],
                    "antonyms": ["riverbank"],
                }
            ],
        },
        {
            "word": "bank",
            "lang_code": "en",
            "pos": "noun",
            "etymology_number": 2,
            "sounds": [{"ipa": "[ˈlaɪ̯v]", "tags": ["Received-Pronunciation"]}],
            "senses": [{"glosses": ["the edge of a river"], "topics": ["geography"]}],
        },
        {
            "word": "bank",
            "lang_code": "en",
            "pos": "noun",
            "etymology_number": 3,
            "senses": [{"glosses": ["a slope of land"]}],
        },
        {
            "word": "alpha",
            "lang_code": "en",
            "pos": "noun",
            "senses": [{"glosses": ["the first letter"]}],
        },
    ]
    source = tmp_path / "entry-stream.jsonl"
    source.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )
    artifact, _ = build_dictionary(
        "en",
        source,
        output=tmp_path / "entry-stream.sqlite3",
        capabilities="lexical,dictionary",
        no_frequency=True,
    )
    return artifact


def test_iter_entries_preserves_entries_and_sense_data(entry_stream_artifact: Path) -> None:
    lexicon = Lexicon.from_path(entry_stream_artifact)
    entries = tuple(lexicon.iter_entries())

    assert entries == tuple(lexicon.iter_entries())
    assert all(isinstance(entry, DictionaryEntry) for entry in entries)
    assert tuple(entry.word for entry in entries) == ("alpha", "bank", "bank", "bank")

    bank_entries = entries[1:]
    assert tuple(entry.pos for entry in bank_entries) == ("noun", "noun", "noun")
    assert tuple(entry.etymology_number for entry in bank_entries) == ("1", "2", "3")
    assert tuple(entry.pronunciations[0].ipa for entry in bank_entries[:2]) == (
        "[ˈlɪv]",
        "[ˈlaɪ̯v]",
    )
    assert tuple(entry.pronunciations[0].tags for entry in bank_entries[:2]) == (
        ("General-American",),
        ("Received-Pronunciation",),
    )
    assert bank_entries[2].pronunciations == ()

    senses = tuple(entry.senses[0] for entry in bank_entries)
    assert all(sense.sense_id for sense in senses)
    assert len({sense.sense_id for sense in senses}) == 3
    assert senses[0].glosses == ("a financial institution",)
    assert set(senses[0].topics) == {"finance", "investment"}
    assert senses[0].tags == ("countable",)
    assert (senses[0].examples[0].text, senses[0].examples[0].translation) == (
        "She went to the bank.",
        "Elle est allée à la banque.",
    )
    assert senses[0].examples[0].kind == "quotation"
    assert senses[0].synonyms[0].word == "depository"
    assert senses[0].synonyms[0].tags == ("rare",)
    assert senses[0].antonyms == ("riverbank",)
    assert senses[2].glosses == ("a slope of land",)


def test_iter_entries_is_lazy_and_closes_connection(
    entry_stream_artifact: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lexicon = Lexicon.from_path(entry_stream_artifact)
    connections: list[sqlite3.Connection] = []
    connect = lexicon._connect

    def tracked_connect() -> sqlite3.Connection:
        connection = connect()
        connections.append(connection)
        return connection

    monkeypatch.setattr(lexicon, "_connect", tracked_connect)

    partial = lexicon.iter_entries()
    assert connections == []
    assert next(partial).word == "alpha"
    assert len(connections) == 1
    partial.close()
    with pytest.raises(sqlite3.ProgrammingError):
        connections[0].execute("SELECT 1")

    complete = lexicon.iter_entries()
    assert len(tuple(complete)) == 4
    assert len(connections) == 2
    with pytest.raises(sqlite3.ProgrammingError):
        connections[1].execute("SELECT 1")
