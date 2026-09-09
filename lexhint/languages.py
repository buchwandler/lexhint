from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

SUPPORTED_BASE_LANGUAGES = (
    "ar",
    "az",
    "bg",
    "ca",
    "ceb",
    "cs",
    "de",
    "el",
    "en",
    "es",
    "fr",
    "ga",
    "he",
    "hi",
    "hu",
    "hy",
    "id",
    "it",
    "ja",
    "ko",
    "ku",
    "la",
    "lt",
    "lv",
    "mr",
    "ms",
    "nl",
    "pl",
    "pt",
    "ro",
    "ru",
    "sv",
    "ta",
    "te",
    "th",
    "tl",
    "tr",
    "uk",
    "ur",
    "vi",
    "zh",
)
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
        "brazil",
        "northeast-brazil",
        "portugal",
        "caipira",
        "paulistana",
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

    @property
    def region(self) -> str:
        return self.code

    @property
    def tag(self) -> str:
        return f"{self.language}-{self.code}"


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
        ("US", "American", "American-English", "American English", "General-American"),
    ),
    "CA": LocaleSpec(
        "CA",
        "en",
        ("en-CA", "en_CA", "ca", "canada"),
        ("Canada", "Canadian", "Canadian-English", "Canadian English"),
    ),
    "BR": LocaleSpec(
        "BR",
        "pt",
        ("pt-BR", "pt_BR", "br", "brazil", "brasil"),
        ("Brazil", "Northeast-Brazil", "Caipira", "Paulistana"),
    ),
    "PT": LocaleSpec(
        "PT",
        "pt",
        ("pt-PT", "pt_PT", "pt", "portugal"),
        ("Portugal",),
    ),
}


def normalize_language(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in SUPPORTED_LANGUAGES:
        raise ValueError(f"unsupported Lexhint language {value!r}")
    return normalized


def _normalize_locale_candidate(value: str) -> str:
    return value.strip().replace("_", "-")


def _locale_spec_for_value(value: str) -> LocaleSpec | None:
    candidate = _normalize_locale_candidate(value)
    folded = candidate.casefold()
    for spec in LOCALES.values():
        if folded in {spec.tag.casefold(), spec.code.casefold()} or folded in {
            alias.replace("_", "-").casefold() for alias in spec.aliases
        }:
            return spec
    return None


def normalize_locale(language: str, value: str | None) -> str | None:
    base_language = normalize_language(language)
    if value is None:
        return None
    candidate = value.strip()
    if not candidate:
        raise ValueError("locale must not be empty")
    spec = _locale_spec_for_value(candidate)
    if spec is None:
        supported = ", ".join(supported_locale_tags(base_language))
        suffix = f"; supported locales for {base_language}: {supported}" if supported else ""
        raise ValueError(f"unsupported locale {value!r} for language {base_language!r}{suffix}")
    if spec.language != base_language:
        raise ValueError(
            f"locale {value!r} is not supported for language {base_language!r}; "
            f"it selects language {spec.language!r}"
        )
    return spec.code


def locale_language(value: str) -> str | None:
    candidate = _normalize_locale_candidate(value)
    parts = candidate.split("-")
    if len(parts) != 2:
        return None
    try:
        language = normalize_language(parts[0])
    except ValueError:
        return None
    return language


def locale_spec(language: str, locale: str | None) -> LocaleSpec | None:
    normalized = normalize_locale(language, locale)
    return LOCALES.get(normalized) if normalized is not None else None


def locale_tag(language: str, locale: str | None) -> str | None:
    spec = locale_spec(language, locale)
    return spec.tag if spec is not None else None


def supported_locale_specs(language: str | None = None) -> tuple[LocaleSpec, ...]:
    if language is None:
        return tuple(LOCALES.values())
    normalized = normalize_language(language)
    return tuple(spec for spec in LOCALES.values() if spec.language == normalized)


def supported_locale_tags(language: str | None = None) -> tuple[str, ...]:
    return tuple(spec.tag for spec in supported_locale_specs(language))


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
    "supported_locale_specs",
    "supported_locale_tags",
    "locale_language",
    "locale_spec",
    "locale_tag",
    "normalize_language",
    "normalize_locale",
]
