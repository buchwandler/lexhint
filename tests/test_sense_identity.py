from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import lexhint.store as store
from lexhint.builder import build_dictionary
from lexhint.extract import dictionary_entries
from lexhint.lexicon import Lexicon
from lexhint.models import DictionaryEntry, Sense
from lexhint.store import (
    SenseIdentityCollision,
    create_schema,
    format_sense_id,
    insert_dictionary_entries,
    sense_identity_anchor,
    stable_sense_int,
)


def entry(gloss: str, *, source_ids: tuple = ()) -> DictionaryEntry:
    return DictionaryEntry("love", "verb", (Sense(glosses=(gloss,), source_ids=source_ids),))


def sense_ids(entries: tuple[DictionaryEntry, ...]) -> dict[str, int]:
    connection = sqlite3.connect(":memory:")
    try:
        create_schema(connection, ("lexical", "dictionary"))
        insert_dictionary_entries(connection, entries, language="en")
        return {
            str(row[1]): int(row[0]) for row in connection.execute("SELECT id, glosses FROM senses")
        }
    finally:
        connection.close()


def test_postprocessed_kaikki_id_is_not_source_provenance() -> None:
    parsed = tuple(
        dictionary_entries(
            {
                "id": "en-love-en-verb-kCNMoC~p",
                "word": "love",
                "lang_code": "en",
                "pos": "verb",
                "senses": [{"id": "website-only", "glosses": ["to care"]}],
            },
            language="en",
        )
    )
    assert parsed[0].senses[0].source_ids == ()


def test_real_source_ids_are_preserved_and_anchor_non_identity_changes() -> None:
    first = Sense(glosses=("first gloss",), source_ids=(store.ExternalSenseId("wikidata", "Q1"),))
    second = Sense(glosses=("edited gloss",), source_ids=first.source_ids)
    assert first.source_ids == second.source_ids
    assert sense_identity_anchor(
        "en", entry("first gloss", source_ids=first.source_ids), first
    ) == sense_identity_anchor("en", entry("edited gloss", source_ids=second.source_ids), second)
    assert stable_sense_int(b"identity") > 0
    assert format_sense_id("en", stable_sense_int(b"identity")).startswith("lh1-en-")


def test_unrelated_input_does_not_renumber_existing_sense() -> None:
    love = entry("to care")
    unrelated = DictionaryEntry("stone", "noun", (Sense(glosses=("a rock",)),))
    assert sense_ids((love,))['["to care"]'] == sense_ids((unrelated, love))['["to care"]']


def test_hash_collision_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(store, "stable_sense_int", lambda anchor: 7)
    connection = sqlite3.connect(":memory:")
    try:
        create_schema(connection, ("lexical", "dictionary"))
        with pytest.raises(SenseIdentityCollision, match="collision"):
            insert_dictionary_entries(
                connection,
                (entry("one"), entry("two")),
                language="en",
            )
    finally:
        connection.close()


def test_build_persists_public_sense_identity_and_provenance(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    source.write_text(
        json.dumps(
            {
                "word": "love",
                "lang_code": "en",
                "pos": "verb",
                "etymology_number": 3,
                "senses": [
                    {
                        "senseid": ["en:care"],
                        "wikidata": ["Q1"],
                        "glosses": ["To care."],
                        "topics": ["music"],
                        "examples": [{"text": "I love it.", "type": "example"}],
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    database, _ = build_dictionary(
        "en", source, output=tmp_path / "schema10.sqlite3", profile="dictionary", no_frequency=True
    )
    lexicon = Lexicon.from_path(database)
    entry_value = lexicon.entries("love")[0]
    sense = entry_value.senses[0]
    assert entry_value.etymology_number == "3"
    assert sense.sense_id and sense.sense_id.startswith("lh1-en-")
    assert sense.source_ids[0].namespace == "wiktionary-senseid"
    assert sense.source_ids[1].namespace == "wikidata"
    assert lexicon.sense_by_id(sense.sense_id).sense == sense
    assert lexicon.topics("love") == ("music",)
