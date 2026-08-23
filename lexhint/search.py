"""Pure, deterministic helpers for Lexhint search indexes and ranking."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

_TOKEN_RE = re.compile(r"[^\W\d_]+(?:[-'][^\W\d_]+)*", re.UNICODE)
_GLOB_META = frozenset("*?[")
_REGEX_META = frozenset(".^$*+?{}[]\\|()")

FIELD_WEIGHTS: dict[str, float] = {
    "glosses": 4.0,
    "topics": 3.0,
    "tags": 2.0,
    "synonyms": 2.0,
    "antonyms": 1.5,
    "examples": 1.0,
}


def normalize_search_text(value: str) -> str:
    """Normalize searchable text using Lexhint's lexical NFC/casefold contract."""

    return unicodedata.normalize("NFC", value).casefold()


def search_tokens(text: str) -> tuple[str, ...]:
    """Return normalized Unicode word tokens in source order."""

    return tuple(
        token
        for match in _TOKEN_RE.finditer(unicodedata.normalize("NFC", text))
        if (token := normalize_search_text(match.group(0)))
    )


def word_ngrams(word: str) -> tuple[str, ...]:
    """Return deduplicated boundary-padded bigrams and trigrams for *word*."""

    normalized = normalize_search_text(word)
    if not normalized:
        return ()
    padded = f"^{normalized}$"
    sizes = (2,) if len(normalized) < 3 else (2, 3)
    result: list[str] = []
    seen: set[str] = set()
    for size in sizes:
        for start in range(len(padded) - size + 1):
            gram = padded[start : start + size]
            if gram not in seen:
                seen.add(gram)
                result.append(gram)
    return tuple(result)


def edit_distance(left: str, right: str, *, max_distance: int | None = None) -> int:
    """Return optimal-string-alignment Damerau distance for two Unicode strings.

    Adjacent transpositions count as one edit. When ``max_distance`` is supplied,
    values greater than the bound are returned as ``max_distance + 1``.
    """

    if max_distance is not None and max_distance < 0:
        raise ValueError("max_distance must be >= 0")
    first = normalize_search_text(left)
    second = normalize_search_text(right)
    if first == second:
        return 0
    if not first:
        distance = len(second)
        return min(distance, max_distance + 1) if max_distance is not None else distance
    if not second:
        distance = len(first)
        return min(distance, max_distance + 1) if max_distance is not None else distance
    if max_distance is not None and abs(len(first) - len(second)) > max_distance:
        return max_distance + 1

    previous_previous: list[int] | None = None
    previous = list(range(len(second) + 1))
    for row_index, left_char in enumerate(first, start=1):
        current = [row_index]
        for column_index, right_char in enumerate(second, start=1):
            substitution = previous[column_index - 1] + (left_char != right_char)
            insertion = current[column_index - 1] + 1
            deletion = previous[column_index] + 1
            value = min(insertion, deletion, substitution)
            if (
                previous_previous is not None
                and row_index > 1
                and column_index > 1
                and left_char == second[column_index - 2]
                and first[row_index - 2] == right_char
            ):
                value = min(value, previous_previous[column_index - 2] + 1)
            current.append(value)
        previous_previous, previous = previous, current

    distance = previous[-1]
    return min(distance, max_distance + 1) if max_distance is not None else distance


def glob_literal_prefix(pattern: str) -> str:
    """Return the literal prefix before the first glob metacharacter."""

    for index, character in enumerate(pattern):
        if character in _GLOB_META:
            return pattern[:index]
    return pattern


def regex_literal_prefix(pattern: str) -> str:
    """Return a safe literal prefix from an anchored regular expression."""

    if not pattern.startswith("^"):
        return ""
    result: list[str] = []
    index = 1
    while index < len(pattern):
        character = pattern[index]
        if character == "\\":
            if index + 1 >= len(pattern):
                return "".join(result)
            escaped = pattern[index + 1]
            if escaped.isalnum() or escaped in "AbBdDsSwWZzG":
                return "".join(result)
            result.append(escaped)
            index += 2
            continue
        if character in _REGEX_META:
            return "".join(result)
        result.append(character)
        index += 1
    return "".join(result)


def capped_term_frequency(term_count: int) -> int:
    """Cap indexed term frequency so repetition cannot dominate relevance."""

    return min(max(term_count, 0), 3)


def weighted_term_score(field: str, term_count: int) -> float:
    """Return the v1 weighted contribution of one matched field term."""

    return FIELD_WEIGHTS[field] * capped_term_frequency(term_count)


def unique_in_order(values: Iterable[str]) -> tuple[str, ...]:
    """Deduplicate strings without changing their first-occurrence order."""

    return tuple(dict.fromkeys(values))
