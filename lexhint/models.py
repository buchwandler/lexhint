from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LexicalSegment:
    """One segment of a compact label."""

    text: str
    known: bool
    frequency_rank: int | None = None


@dataclass(frozen=True, slots=True)
class Example:
    """A usage example attached to a dictionary sense."""

    text: str
    translation: str | None = None


@dataclass(frozen=True, slots=True)
class WordInfo:
    """Dictionary membership and optional corpus frequency evidence."""

    word: str
    known: bool
    frequency_rank: int | None = None
    frequency_count: int | None = None


@dataclass(frozen=True, slots=True)
class Form:
    """An inflected or alternate form of a dictionary entry."""

    form: str
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Pronunciation:
    """An IPA pronunciation variant supplied by the source dictionary."""

    ipa: str
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Sense:
    """A curated dictionary sense extracted from Wiktextract/Kaikki JSONL."""

    glosses: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    examples: tuple[Example, ...] = ()
    synonyms: tuple[str, ...] = ()
    antonyms: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DictionaryEntry:
    """One ordered lexical entry containing one or more ordered senses."""

    word: str
    pos: str
    senses: tuple[Sense, ...]
    forms: tuple[Form, ...] = ()
    pronunciations: tuple[Pronunciation, ...] = ()
    etymology: str | None = None


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
    frequency_rows: int = 0
    frequency_matches: int = 0
    frequency_total_tokens: int = 0


@dataclass(frozen=True, slots=True)
class DictionaryFetchResult:
    """Result of fetching or reusing one dictionary word page and its rich senses."""

    word: str
    status: str
    senses: int
    source_url: str
    cached: bool
