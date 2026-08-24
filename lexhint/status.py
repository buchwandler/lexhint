from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .lexicon import Lexicon


@dataclass(frozen=True, slots=True)
class ArtifactStatus:
    language: str
    path: str
    size_bytes: int
    schema_version: str
    coverage: str
    profile: str
    capabilities: tuple[str, ...]
    counts: dict[str, int | None]
    frequency: dict[str, str]
    provenance: dict[str, str]
    built_at: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _has_table(connection: sqlite3.Connection, name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _count(connection: sqlite3.Connection, query: str) -> int:
    row = connection.execute(query).fetchone()
    return int(row[0]) if row is not None else 0


def read_artifact_status(
    language: str | None = None,
    *,
    variant: str | None = None,
    dataset_version: str | None = None,
    path: str | Path | None = None,
) -> ArtifactStatus:
    if language is None and path is None:
        language = "en"
    if language is None:
        assert path is not None
        if variant is not None or dataset_version is not None:
            raise ValueError("path cannot be combined with variant or dataset_version")
        lexicon = Lexicon.from_path(path)
    else:
        lexicon = Lexicon(
            language,
            variant=variant,
            dataset_version=dataset_version,
            path=path,
        )
    metadata = lexicon.metadata
    with closing(lexicon._connect()) as connection:
        has_semantic = _has_table(connection, "lexeme_domains")
        has_dictionary = _has_table(connection, "entries") and _has_table(connection, "senses")
        has_relations = _has_table(connection, "headword_relations")
        counts: dict[str, int | None] = {
            "lexemes": _count(connection, "SELECT COUNT(*) FROM lexemes"),
            "semantic_rows": (
                _count(connection, "SELECT COUNT(*) FROM lexeme_domains") if has_semantic else None
            ),
            "entries": _count(connection, "SELECT COUNT(*) FROM entries")
            if has_dictionary
            else None,
            "senses": _count(connection, "SELECT COUNT(*) FROM senses") if has_dictionary else None,
            "relations": (
                _count(connection, "SELECT COUNT(*) FROM headword_relations")
                if has_relations
                else None
            ),
            "frequency_lexemes": _count(
                connection, "SELECT COUNT(*) FROM lexemes WHERE corpus_rank IS NOT NULL"
            ),
        }
    return ArtifactStatus(
        language=lexicon.language,
        path=str(lexicon.path),
        size_bytes=lexicon.path.stat().st_size,
        schema_version=metadata.get("schema_version", ""),
        coverage=metadata.get("coverage", ""),
        profile=metadata.get("profile", metadata.get("dictionary_profile", "")),
        capabilities=lexicon.capabilities,
        counts=counts,
        frequency={
            "source": metadata.get("frequency_source", ""),
            "corpus": metadata.get("frequency_corpus", ""),
            "revision": metadata.get("frequency_source_revision", ""),
            "source_sha256": metadata.get("frequency_source_sha256", ""),
        },
        provenance={
            key: metadata.get(key, "")
            for key in (
                "schema_version",
                "language",
                "coverage",
                "profile",
                "capabilities",
                "dataset_version",
                "builder_version",
                "built_at",
                "dictionary_source",
                "dictionary_source_sha256",
                "dictionary_source_format",
                "dictionary_source_contract",
                "frequency_source",
                "frequency_source_sha256",
            )
        },
        built_at=metadata.get("built_at", ""),
    )


__all__ = ["ArtifactStatus", "read_artifact_status"]
