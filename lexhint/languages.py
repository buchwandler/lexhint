from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

SUPPORTED_BASE_LANGUAGES = ("cs", "de", "en", "es", "fr", "it", "pt")
SUPPORTED_LANGUAGES = frozenset(SUPPORTED_BASE_LANGUAGES)
REGIONAL_SOURCE_TAGS = frozenset(
    {
        "uk",
        "british",
        "british-english",
        "british english",
        "us",
        "american",
        "american-english",
        "american english",
        "general-american",
        "canada",
        "canadian",
        "canadian-english",
        "canadian english",
    }
)


def supported_base_languages() -> tuple[str, ...]:
    return SUPPORTED_BASE_LANGUAGES


@dataclass(frozen=True, slots=True)
class LocaleSpec:
    code: str
    language: str
    aliases: tuple[str, ...]
    preferred_source_tags: tuple[str, ...]


LOCALES: dict[str, LocaleSpec] = {
    "GB": LocaleSpec(
        "GB",
        "en",
        ("en-GB", "en_GB", "gb", "uk"),
        (
            "UK",
            "British",
            "British-English",
            "British English",
            "Received-Pronunciation",
            "England",
            "London",
            "Southern-England",
            "Northern-England",
            "Midlands",
            "Scotland",
            "Wales",
            "Northern-Ireland",
        ),
    ),
    "US": LocaleSpec(
        "US",
        "en",
        ("en-US", "en_US", "us"),
        (
            "US",
            "American",
            "American-English",
            "American English",
            "General-American",
        ),
    ),
    "CA": LocaleSpec(
        "CA",
        "en",
        ("en-CA", "en_CA", "ca", "canada"),
        ("Canada", "Canadian", "Canadian-English", "Canadian English"),
    ),
}


def normalize_language(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in SUPPORTED_LANGUAGES:
        raise ValueError(f"unsupported Lexhint language {value!r}")
    return normalized


def normalize_locale(language: str, value: str | None) -> str | None:
    base_language = normalize_language(language)
    if value is None:
        return None
    candidate = value.strip()
    if not candidate:
        raise ValueError("locale must not be empty")
    for spec in LOCALES.values():
        if candidate.upper() == spec.code or candidate.lower() in {
            alias.lower() for alias in spec.aliases
        }:
            if spec.language != base_language:
                raise ValueError(
                    f"locale {value!r} is not supported for language {base_language!r}"
                )
            return spec.code
    raise ValueError(f"unsupported locale {value!r} for language {base_language!r}")


def locale_spec(language: str, locale: str | None) -> LocaleSpec | None:
    normalized = normalize_locale(language, locale)
    return LOCALES.get(normalized) if normalized is not None else None


def normalize_source_region_tag(value: str) -> str:
    normalized = value.strip().casefold()
    normalized = re.sub(r"[\s_]+", "-", normalized)
    return re.sub(r"-+", "-", normalized)


REGION_TAG_ALIASES: dict[str, frozenset[str]] = {}


def _normalized_region_tags(values: Iterable[str]) -> set[str]:
    normalized = {normalize_source_region_tag(value) for value in values}
    for canonical, aliases in REGION_TAG_ALIASES.items():
        if normalized & {normalize_source_region_tag(alias) for alias in aliases}:
            normalized.add(canonical)
    return normalized


def source_tags_match_region(tags: tuple[str, ...], region: str) -> bool:
    accepted = _normalized_region_tags((region,))
    return bool(_normalized_region_tags(tags) & accepted)


def source_tags_match_locale(tags: tuple[str, ...], language: str, locale: str) -> bool:
    spec = locale_spec(language, locale)
    if spec is None:
        return False
    accepted = _normalized_region_tags(set(spec.preferred_source_tags))
    return bool(_normalized_region_tags(tags) & accepted)


def is_regional_source_tag(value: str) -> bool:
    return normalize_source_region_tag(value) in _normalized_region_tags(REGIONAL_SOURCE_TAGS)


__all__ = [
    "LOCALES",
    "LocaleSpec",
    "REGIONAL_SOURCE_TAGS",
    "REGION_TAG_ALIASES",
    "SUPPORTED_BASE_LANGUAGES",
    "SUPPORTED_LANGUAGES",
    "normalize_source_region_tag",
    "source_tags_match_locale",
    "source_tags_match_region",
    "is_regional_source_tag",
    "supported_base_languages",
    "locale_spec",
    "normalize_language",
    "normalize_locale",
]
