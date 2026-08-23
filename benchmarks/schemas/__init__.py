"""SQLite schema adapters shipped with the benchmark."""

from .current_v8 import CurrentV8Adapter


def get_adapter(name: str, *, capabilities: tuple[str, ...] | None = None):
    if name == "current-v8":
        return CurrentV8Adapter(capabilities=capabilities)
    if name == "current-v8-without-rowid-search":
        from .compact_experiment import WithoutRowidSearchAdapter

        return WithoutRowidSearchAdapter(capabilities=capabilities)
    raise ValueError(f"unknown benchmark schema: {name}")


__all__ = ["CurrentV8Adapter", "get_adapter"]
