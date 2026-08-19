from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Segment:
    """One lexical or unknown segment of an identifier-like string."""

    text: str
    known: bool
    rank: int | None = None


@dataclass(frozen=True, slots=True)
class Sense:
    """A compact dictionary sense extracted from Wiktextract/Kaikki JSONL."""

    word: str
    pos: str
    glosses: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TopicScore:
    """Context score for one dictionary topic."""

    topic: str
    score: float
    cues: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ContextSupport:
    """Evidence that nearby dictionary senses support a requested topic."""

    topic: str
    score: float
    cues: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DictionaryBuildStats:
    """Summary of a streaming dictionary build."""

    scanned_entries: int
    kept_entries: int
    words: int
    senses: int
