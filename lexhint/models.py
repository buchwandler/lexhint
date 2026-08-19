from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LexicalSegment:
    """One segment of a compact label.

    ``in_lexicon`` is lexical-resource evidence only.  It does not decide
    whether the segment is a word, acronym, brand, name, or pronunciation.
    """

    text: str
    in_lexicon: bool
    frequency_rank: int | None = None


@dataclass(frozen=True, slots=True)
class Sense:
    """A compact dictionary sense extracted from Wiktextract/Kaikki JSONL."""

    word: str
    pos: str
    glosses: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ContextCue:
    """One nearby token contributing dictionary topic evidence."""

    text: str
    start: int
    end: int
    distance: int
    weight: float


@dataclass(frozen=True, slots=True)
class TopicEvidence:
    """Soft, diagnostic context evidence for one dictionary topic."""

    topic: str
    score: float
    cues: tuple[ContextCue, ...]


@dataclass(frozen=True, slots=True)
class DictionaryBuildStats:
    """Summary of a streaming dictionary build."""

    scanned_entries: int
    kept_entries: int
    words: int
    senses: int


@dataclass(frozen=True, slots=True)
class DictionaryFetchResult:
    """Result of fetching or reusing one dictionary word page and its compact senses."""

    word: str
    status: str
    senses: int
    source_url: str
    cached: bool
