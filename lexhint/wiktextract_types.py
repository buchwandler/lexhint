"""Narrow Lexhint-owned types for the Wiktextract/Kaikki JSONL contract."""

from __future__ import annotations

from typing import TypedDict


class WiktextractExample(TypedDict, total=False):
    text: str
    translation: str
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
    topics: list[str]
    tags: list[str]
    raw_tags: list[str]
    examples: list[WiktextractExample]
    synonyms: list[WiktextractRelated]
    antonyms: list[WiktextractRelated]
    form_of: list[WiktextractRelation]
    alt_of: list[WiktextractRelation]


class WiktextractEntry(TypedDict, total=False):
    word: str
    lang_code: str
    pos: str
    senses: list[WiktextractSense]
    topics: list[str]
    forms: list[WiktextractForm]
    sounds: list[WiktextractSound]
    etymology_text: str
    etymology: str
    redirects: list[str | WiktextractRelation]


ENTRY_FIELDS = frozenset(WiktextractEntry.__annotations__)
SENSE_FIELDS = frozenset(WiktextractSense.__annotations__)
RETAINED_ENTRY_FIELDS = frozenset(
    {
        "word",
        "lang_code",
        "pos",
        "senses",
        "topics",
        "forms",
        "sounds",
        "etymology_text",
        "etymology",
        "redirects",
    }
)
RETAINED_SENSE_FIELDS = frozenset(
    {"glosses", "topics", "tags", "examples", "synonyms", "antonyms", "alt_of", "form_of"}
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
