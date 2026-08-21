from __future__ import annotations

from dataclasses import dataclass

SUPPORTED_BASE_LANGUAGES = ("cs", "de", "en", "es", "fr", "it", "pt")
SUPPORTED_LANGUAGES = frozenset(SUPPORTED_BASE_LANGUAGES)


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
        ("UK", "British", "British-English", "British English"),
    ),
    "US": LocaleSpec(
        "US",
        "en",
        ("en-US", "en_US", "us"),
        ("US", "American", "American-English", "American English"),
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


__all__ = [
    "LOCALES",
    "LocaleSpec",
    "SUPPORTED_BASE_LANGUAGES",
    "SUPPORTED_LANGUAGES",
    "supported_base_languages",
    "locale_spec",
    "normalize_language",
    "normalize_locale",
]
