from __future__ import annotations

import json
from pathlib import Path

from lexhint import HeadwordRelation, Lexicon
from lexhint.builder import build_dictionary
from lexhint.cli import main


def relation_source(path: Path) -> Path:
    path.write_text(
        "\n".join(
            json.dumps(value)
            for value in (
                {
                    "word": "color",
                    "lang_code": "en",
                    "pos": "noun",
                    "redirects": ["colour"],
                    "senses": [{"glosses": ["A hue."]}],
                },
                {
                    "word": "colours",
                    "lang_code": "en",
                    "pos": "noun",
                    "senses": [{"glosses": ["Plural hue."], "form_of": [{"word": "color"}]}],
                },
                {
                    "word": "colour",
                    "lang_code": "en",
                    "pos": "noun",
                    "senses": [
                        {
                            "glosses": ["Alternative spelling."],
                            "alt_of": [{"word": "color", "tags": ["UK"]}],
                        }
                    ],
                },
            )
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def test_schema_10_relation_api_is_explicit_and_deduplicated(tmp_path: Path) -> None:
    database, stats = build_dictionary(
        "en",
        relation_source(tmp_path / "relations.jsonl"),
        output=tmp_path / "en.sqlite3",
        no_frequency=True,
    )
    lexicon = Lexicon.from_path(database)
    assert lexicon.schema_version == "10"
    assert stats.relation_rows == 3
    assert lexicon.relations("color") == (HeadwordRelation("color", "colour", "redirect"),)
    assert lexicon.relations("colour") == (
        HeadwordRelation("colour", "color", "alternative", ("UK",)),
    )
    assert lexicon.resolve_headword("colours") == ("color",)
    assert lexicon.entries("colour")[0].senses[0].glosses == ("Alternative spelling.",)


def test_relation_cli_supports_json_and_resolution(tmp_path: Path, capsys) -> None:
    database, _ = build_dictionary(
        "en",
        relation_source(tmp_path / "relations.jsonl"),
        output=tmp_path / "en.sqlite3",
        no_frequency=True,
    )
    assert main(["--json", "dictionary", "relations", "colour", "--path", str(database)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["relations"][0]["target"] == "color"
    assert main(["dictionary", "resolve", "colours", "--path", str(database)]) == 0
    assert capsys.readouterr().out.strip() == "color"


def test_entry_relations_and_incoming_lookup(tmp_path: Path) -> None:
    source = tmp_path / "entry-relations.jsonl"
    source.write_text(
        json.dumps(
            {
                "word": "love",
                "lang_code": "en",
                "pos": "verb",
                "synonyms": [
                    {"word": "adore", "tags": ["formal"]},
                    {"word": "adore", "tags": ["rare"]},
                ],
                "antonyms": ["hate"],
                "hypernyms": ["feel"],
                "hyponyms": ["like"],
                "related": ["affection"],
                "derived": ["lover"],
                "senses": [{"glosses": ["to care"], "synonyms": ["cherish"]}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    database, _ = build_dictionary(
        "en", source, output=tmp_path / "entry-relations.sqlite3", no_frequency=True
    )
    lexicon = Lexicon.from_path(database)
    relations = lexicon.relations("love")
    assert {(value.target, value.relation) for value in relations} == {
        ("adore", "synonym"),
        ("hate", "antonym"),
        ("feel", "hypernym"),
        ("like", "hyponym"),
        ("affection", "related"),
    }
    assert next(value for value in relations if value.target == "adore").tags == ("formal", "rare")
    assert lexicon.incoming_relations("adore")[0].source == "love"
    assert lexicon.entries("love")[0].senses[0].synonyms == ("cherish",)
