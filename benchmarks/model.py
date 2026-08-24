"""Logical data model used by every benchmark schema adapter."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class SyntheticProfile:
    """All knobs that determine the generated logical dictionary shape."""

    name: str = "synthetic"
    seed: int = 1
    lexemes: int = 1000
    frequency_coverage: float = 0.5
    entries_per_lexeme_mean: float = 1.2
    senses_per_entry_mean: float = 1.8
    headword_length_mean: float = 8.0
    headword_length_stddev: float = 2.5
    etymology_probability: float = 0.3
    etymology_length_mean: int = 80
    forms_per_entry_mean: float = 1.0
    pronunciations_per_entry_mean: float = 0.5
    glosses_per_sense_mean: float = 1.2
    gloss_length_mean: int = 48
    topics_per_sense_mean: float = 0.35
    tags_per_sense_mean: float = 0.4
    examples_per_sense_mean: float = 0.5
    example_length_mean: int = 72
    example_translation_probability: float = 0.05
    synonyms_per_sense_mean: float = 0.35
    antonyms_per_sense_mean: float = 0.12
    semantic_coverage: float = 0.2
    domains_per_semantic_lexeme_mean: float = 1.3
    vocabulary_size: int = 256
    token_length_mean: float = 6.0
    search_term_density: float = 1.0
    relations_per_lexeme_mean: float = 0.35
    redirect_fraction: float = 0.03
    alternative_fraction: float = 0.08
    form_of_fraction: float = 0.24
    relation_tag_bytes_mean: int = 10
    batch_size: int = 1000
    assumption_note: str = ""

    @classmethod
    def from_dict(cls, values: dict[str, Any]) -> SyntheticProfile:
        fields = {field.name for field in cls.__dataclass_fields__.values()}
        unknown = set(values) - fields
        if unknown:
            raise ValueError(f"unknown profile fields: {sorted(unknown)}")
        profile = cls(**values)
        profile.validate()
        return profile

    @classmethod
    def from_json(cls, path: str | Path) -> SyntheticProfile:
        with Path(path).open(encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, dict):
            raise ValueError(f"profile must be a JSON object: {path}")
        return cls.from_dict(value)

    def validate(self) -> None:
        if self.lexemes < 1:
            raise ValueError("lexemes must be positive")
        if self.seed < 0:
            raise ValueError("seed must be non-negative")
        for name in (
            "frequency_coverage",
            "etymology_probability",
            "example_translation_probability",
            "semantic_coverage",
            "search_term_density",
            "redirect_fraction",
            "alternative_fraction",
            "form_of_fraction",
        ):
            value = getattr(self, name)
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        for name in (
            "entries_per_lexeme_mean",
            "senses_per_entry_mean",
            "forms_per_entry_mean",
            "pronunciations_per_entry_mean",
            "glosses_per_sense_mean",
            "topics_per_sense_mean",
            "tags_per_sense_mean",
            "examples_per_sense_mean",
            "synonyms_per_sense_mean",
            "antonyms_per_sense_mean",
            "domains_per_semantic_lexeme_mean",
            "headword_length_mean",
            "headword_length_stddev",
            "token_length_mean",
            "relations_per_lexeme_mean",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        for name in (
            "etymology_length_mean",
            "gloss_length_mean",
            "example_length_mean",
            "vocabulary_size",
            "batch_size",
            "relation_tag_bytes_mean",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")

    def canonical_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class SyntheticLexeme:
    word: str
    display_word: str
    entry_count: int
    has_lowercase: bool
    has_titlecase: bool
    has_uppercase: bool
    corpus_count: int | None
    corpus_rank: int | None


@dataclass(frozen=True, slots=True)
class SyntheticEntry:
    entry_id: int
    word: str
    display_word: str
    pos: str
    entry_index: int
    etymology: str
    forms_json: str
    pronunciations_json: str


@dataclass(frozen=True, slots=True)
class SyntheticSense:
    sense_id: int
    entry_id: int
    word: str
    sense_index: int
    glosses_json: str
    topics_json: str
    tags_json: str
    examples_json: str
    synonyms_json: str
    antonyms_json: str
    search_fields: tuple[tuple[str, tuple[str, ...]], ...]

    def field_values(self, field: str) -> tuple[str, ...]:
        return dict(self.search_fields).get(field, ())


@dataclass(frozen=True, slots=True)
class SyntheticRelation:
    source: str
    target: str
    relation: str
    tags_json: str


class SyntheticDataset:
    """A repeatable logical dataset whose rows are generated on demand."""

    def __init__(self, profile: SyntheticProfile):
        profile.validate()
        self.profile = profile

    def iter_lexemes(self) -> Iterator[SyntheticLexeme]:
        from .generate import SyntheticGenerator

        yield from SyntheticGenerator(self.profile).iter_lexemes()

    def iter_entries(self) -> Iterator[SyntheticEntry]:
        from .generate import SyntheticGenerator

        yield from SyntheticGenerator(self.profile).iter_entries()

    def iter_relations(self) -> Iterator[SyntheticRelation]:
        from .generate import SyntheticGenerator

        yield from SyntheticGenerator(self.profile).iter_relations()

    def iter_senses(self) -> Iterator[SyntheticSense]:
        from .generate import SyntheticGenerator

        yield from SyntheticGenerator(self.profile).iter_senses()

    def counts(self) -> dict[str, int]:
        from .generate import SyntheticGenerator

        return SyntheticGenerator(self.profile).counts()

    def query_corpus(self) -> dict[str, list[str]]:
        from .generate import SyntheticGenerator

        return SyntheticGenerator(self.profile).query_corpus()

    def relation_counts(self) -> dict[str, int]:
        from .generate import SyntheticGenerator

        return SyntheticGenerator(self.profile).relation_counts()
