"""SQLite schema adapters shipped with the benchmark."""

from .current_v8 import CurrentV8Adapter
from .current_v8_relations import CurrentV8RelationsAdapter
from .current_v9 import CurrentV9Adapter
from .current_v9_readonly_finalized import CurrentV9ReadonlyFinalizedAdapter
from .current_v9_without_rowid import CurrentV9WithoutRowidAdapter
from .schema10_candidate import Schema10CandidateAdapter


def get_adapter(name: str, *, capabilities: tuple[str, ...] | None = None):
    if name == "current-v8":
        return CurrentV8Adapter(capabilities=capabilities)
    if name == "current-v8-without-rowid-search":
        from .compact_experiment import WithoutRowidSearchAdapter

        return WithoutRowidSearchAdapter(capabilities=capabilities)
    if name == "current-v8-relations":
        return CurrentV8RelationsAdapter(capabilities=capabilities)
    if name == "current-v9":
        return CurrentV9Adapter(capabilities=capabilities)
    if name == "current-v9-without-rowid":
        return CurrentV9WithoutRowidAdapter(capabilities=capabilities)
    if name == "current-v9-readonly-finalized":
        return CurrentV9ReadonlyFinalizedAdapter(capabilities=capabilities)
    if name == "schema10-candidate":
        return Schema10CandidateAdapter(capabilities=capabilities)
    raise ValueError(f"unknown benchmark schema: {name}")


__all__ = [
    "CurrentV8Adapter",
    "CurrentV8RelationsAdapter",
    "CurrentV9Adapter",
    "CurrentV9ReadonlyFinalizedAdapter",
    "CurrentV9WithoutRowidAdapter",
    "Schema10CandidateAdapter",
    "get_adapter",
]
