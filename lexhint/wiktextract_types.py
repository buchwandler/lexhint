"""Narrow Lexhint-owned types for the Wiktextract/Kaikki JSONL contract."""

from __future__ import annotations

from typing import TypedDict


class WiktextractExample(TypedDict, total=False):
    text: str
    translation: str
    type: str
    kind: str
    tags: list[str]
    raw_tags: list[str]


class WiktextractRelated(TypedDict, total=False):
    word: str
    tags: list[str]
    raw_tags: list[str]


class WiktextractForm(TypedDict, total=False):
    form: str
    tags: list[str]
    raw_tags: list[str]


class WiktextractSound(TypedDict, total=False):
    ipa: str
    tags: list[str]
    raw_tags: list[str]


class WiktextractRelation(WiktextractRelated, total=False):
    target: str


class WiktextractSense(TypedDict, total=False):
    glosses: list[str]
    raw_glosses: list[str]
    senseid: list[str]
    wikidata: list[str]
    topics: list[str]
    tags: list[str]
    raw_tags: list[str]
    examples: list[WiktextractExample]
    synonyms: list[WiktextractRelated]
    antonyms: list[WiktextractRelated]
    hypernyms: list[WiktextractRelated]
    hyponyms: list[WiktextractRelated]
    related: list[WiktextractRelated]
    coordinate_terms: list[WiktextractRelated]
    form_of: list[WiktextractRelation]
    alt_of: list[WiktextractRelation]


class WiktextractEntry(TypedDict, total=False):
    word: str
    lang_code: str
    pos: str
    etymology_number: str | int
    senses: list[WiktextractSense]
    topics: list[str]
    forms: list[WiktextractForm]
    sounds: list[WiktextractSound]
    etymology_text: str
    etymology: str
    redirects: list[str | WiktextractRelation]
    synonyms: list[WiktextractRelated]
    antonyms: list[WiktextractRelated]
    hypernyms: list[WiktextractRelated]
    hyponyms: list[WiktextractRelated]
    related: list[WiktextractRelated]
    derived: list[WiktextractRelated]


ENTRY_FIELDS = frozenset(WiktextractEntry.__annotations__)
SENSE_FIELDS = frozenset(WiktextractSense.__annotations__)
RETAINED_ENTRY_FIELDS = frozenset(
    {
        "word",
        "lang_code",
        "pos",
        "etymology_number",
        "senses",
        "topics",
        "forms",
        "sounds",
        "etymology_text",
        "etymology",
        "redirects",
        "synonyms",
        "antonyms",
        "hypernyms",
        "hyponyms",
        "related",
    }
)
RETAINED_SENSE_FIELDS = frozenset(
    {
        "glosses",
        "topics",
        "tags",
        "examples",
        "senseid",
        "wikidata",
        "synonyms",
        "antonyms",
        "alt_of",
        "form_of",
    }
)


__all__ = [
    "ENTRY_FIELDS",
    "RETAINED_ENTRY_FIELDS",
    "RETAINED_SENSE_FIELDS",
    "SENSE_FIELDS",
    "WiktextractEntry",
    "WiktextractExample",
    "WiktextractForm",
    "WiktextractRelated",
    "WiktextractRelation",
    "WiktextractSense",
    "WiktextractSound",
]
