from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True, slots=True)
class LexicalSegment:
    text: str
    known: bool
    frequency_rank: int | None = None


@dataclass(frozen=True, slots=True)
class WordEvidence:
    text: str
    known: bool
    frequency_rank: int | None = None
    frequency_count: int | None = None
    has_lowercase: bool = False
    has_titlecase: bool = False
    has_uppercase: bool = False

    @property
    def uppercase_only(self) -> bool:
        return (
            self.known and self.has_uppercase and not self.has_lowercase and not self.has_titlecase
        )


class SemanticDomain(str, Enum):
    COMPUTING = "computing"
    COMMUNICATIONS = "communications"
    FINANCE = "finance"
    LAW = "law"
    SPORTS = "sports"
    MUSIC = "music"
    BIOLOGY = "biology"
    MEDICINE = "medicine"
    CHEMISTRY = "chemistry"
    GEOGRAPHY = "geography"


@dataclass(frozen=True, slots=True)
class Example:
    text: str
    translation: str | None = None


@dataclass(frozen=True, slots=True)
class Form:
    form: str
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Pronunciation:
    ipa: str
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RelatedTerm:
    word: str
    relation: str
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Sense:
    glosses: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    examples: tuple[Example, ...] = ()
    synonyms: tuple[str | RelatedTerm, ...] = ()
    antonyms: tuple[str | RelatedTerm, ...] = ()


@dataclass(frozen=True, slots=True)
class DictionaryEntry:
    word: str
    pos: str
    senses: tuple[Sense, ...]
    forms: tuple[Form, ...] = ()
    pronunciations: tuple[Pronunciation, ...] = ()
    etymology: str | None = None


@dataclass(frozen=True, slots=True)
class ContextCue:
    text: str
    start: int
    end: int
    distance: int
    weight: float


@dataclass(frozen=True, slots=True)
class DomainEvidence:
    domain: SemanticDomain
    score: float
    cues: tuple[ContextCue, ...]


@dataclass(frozen=True, slots=True)
class DictionaryBuildStats:
    language: str = ""
    capabilities: tuple[str, ...] = ()
    scanned_entries: int = 0
    kept_entries: int = 0
    words: int = 0
    senses: int = 0
    semantic_rows: int = 0
    frequency_rows: int = 0
    frequency_matches: int = 0
    frequency_total_tokens: int = 0
    entries: int = 0
