"""SQLite schema adapters shipped with the benchmark."""

from .current_v8 import CurrentV8Adapter
from .current_v8_relations import CurrentV8RelationsAdapter


def get_adapter(name: str, *, capabilities: tuple[str, ...] | None = None):
    if name == "current-v8":
        return CurrentV8Adapter(capabilities=capabilities)
    if name == "current-v8-without-rowid-search":
        from .compact_experiment import WithoutRowidSearchAdapter

        return WithoutRowidSearchAdapter(capabilities=capabilities)
    if name == "current-v8-relations":
        return CurrentV8RelationsAdapter(capabilities=capabilities)
    raise ValueError(f"unknown benchmark schema: {name}")


__all__ = ["CurrentV8Adapter", "CurrentV8RelationsAdapter", "get_adapter"]
