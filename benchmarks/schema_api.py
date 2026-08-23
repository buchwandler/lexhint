"""Public protocol and shared build types for benchmark schema adapters."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Protocol

from .model import SyntheticDataset


@dataclass(slots=True)
class BuildMetrics:
    phases: dict[str, dict[str, float | int]] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)


class SchemaAdapter(Protocol):
    name: str
    description: str
    source_schema_version: str
    supported_workloads: frozenset[str]

    def create(self, connection: sqlite3.Connection) -> None: ...

    def populate(
        self, connection: sqlite3.Connection, dataset: SyntheticDataset, *, batch_size: int
    ) -> BuildMetrics: ...

    def finalize(self, connection: sqlite3.Connection) -> None: ...

    def exact_lookup(self, connection: sqlite3.Connection, word: str) -> object: ...

    def complete(self, connection: sqlite3.Connection, prefix: str, limit: int) -> object: ...

    def suggest(self, connection: sqlite3.Connection, query: str, limit: int) -> object: ...

    def dictionary_lookup(self, connection: sqlite3.Connection, word: str) -> object: ...

    def definition_search(
        self, connection: sqlite3.Connection, terms: tuple[str, ...], *, match: str, limit: int
    ) -> object: ...


def capability_set(capabilities: tuple[str, ...] | list[str] | None) -> frozenset[str]:
    """Expand friendly capability names into persisted schema capabilities."""

    selected = set(capabilities or ("rich",))
    if "rich" in selected:
        selected.update(("lexical", "semantic", "dictionary", "search"))
    if "dictionary" in selected:
        selected.update(("lexical", "semantic", "dictionary"))
    if "runtime" in selected:
        selected.update(("lexical", "semantic"))
    if "search" in selected:
        selected.update(("lexical", "semantic", "dictionary", "search"))
    return frozenset(selected)
