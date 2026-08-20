from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

CAPABILITY_ORDER = ("lexical", "semantic", "dictionary")
CAPABILITIES = frozenset(CAPABILITY_ORDER)
PROFILES = {
    "runtime": ("lexical", "semantic"),
    "rich": ("lexical", "semantic", "dictionary"),
}


@dataclass(frozen=True, slots=True)
class CapabilitySelection:
    capabilities: tuple[str, ...]
    profile: str


def normalize_capabilities(
    capabilities: str | Iterable[str] | None = None, *, profile: str | None = None
) -> CapabilitySelection:
    if capabilities is not None and profile is not None:
        raise ValueError("choose either --profile or --capabilities, not both")
    if profile is not None:
        if profile not in PROFILES:
            raise ValueError(f"unknown profile {profile!r}; choose runtime or rich")
        selected = PROFILES[profile]
    elif capabilities is None:
        selected = CAPABILITY_ORDER
        profile = "rich"
    else:
        values = capabilities.split(",") if isinstance(capabilities, str) else tuple(capabilities)
        if not values or any(not value for value in values):
            raise ValueError("capabilities must not be empty")
        unknown = sorted(set(values) - CAPABILITIES)
        if unknown:
            raise ValueError(f"unknown capability {unknown[0]!r}")
        selected = tuple(dict.fromkeys(values))
        profile = (
            "runtime"
            if selected == PROFILES["runtime"]
            else "rich"
            if selected == PROFILES["rich"]
            else "custom"
        )
    canonical = tuple(capability for capability in CAPABILITY_ORDER if capability in selected)
    if "lexical" not in canonical:
        missing = "semantic" if "semantic" in selected else "dictionary"
        raise ValueError(f"capability {missing!r} requires capability 'lexical'")
    return CapabilitySelection(canonical, profile or "custom")


def has_capability(capabilities: Iterable[str], capability: str) -> bool:
    return capability in set(capabilities)
