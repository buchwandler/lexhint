from __future__ import annotations

from dataclasses import dataclass, field
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
class HeadwordRelation:
    source: str
    target: str
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
class DictionarySearchHit:
    word: str
    pos: str
    sense_index: int
    glosses: tuple[str, ...]
    score: float
    matched_terms: tuple[str, ...] = ()
    matched_fields: tuple[str, ...] = ()


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
    search_lexeme_rows: int = 0
    search_sense_rows: int = 0
    relation_rows: int = 0


@dataclass(slots=True)
class ExtractionDiagnostics:
    source_records: int = 0
    language_records: int = 0
    entries_without_word: int = 0
    entries_without_senses: int = 0
    senses_seen: int = 0
    senses_retained: int = 0
    senses_without_retained_content: int = 0
    entries_with_etymology: int = 0
    entries_with_forms: int = 0
    entries_with_ipa: int = 0
    entries_with_relations: int = 0
    accepted_entries: int = 0
    accepted_senses: int = 0
    relation_candidates: int = 0
    source_fields: dict[str, int] = field(default_factory=dict)
    retained_fields: dict[str, int] = field(default_factory=dict)
    dropped_fields: dict[str, int] = field(default_factory=dict)

    @staticmethod
    def _increment(values: dict[str, int], field_name: str) -> None:
        values[field_name] = values.get(field_name, 0) + 1

    def record_fields(self, fields: set[str], retained: set[str]) -> None:
        for field_name in fields:
            self._increment(self.source_fields, field_name)
            if field_name in retained:
                self._increment(self.retained_fields, field_name)
            else:
                self._increment(self.dropped_fields, field_name)

    def as_dict(self) -> dict[str, object]:
        return {
            "source_records": self.source_records,
            "language_records": self.language_records,
            "entries_without_word": self.entries_without_word,
            "entries_without_senses": self.entries_without_senses,
            "senses_seen": self.senses_seen,
            "senses_retained": self.senses_retained,
            "senses_without_retained_content": self.senses_without_retained_content,
            "entries_with_etymology": self.entries_with_etymology,
            "entries_with_forms": self.entries_with_forms,
            "entries_with_ipa": self.entries_with_ipa,
            "entries_with_relations": self.entries_with_relations,
            "accepted_entries": self.accepted_entries,
            "accepted_senses": self.accepted_senses,
            "relation_candidates": self.relation_candidates,
            "source_fields": dict(sorted(self.source_fields.items())),
            "retained_fields": dict(sorted(self.retained_fields.items())),
            "dropped_fields": dict(sorted(self.dropped_fields.items())),
        }
