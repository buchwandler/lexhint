from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterable, Mapping
from contextlib import closing
from importlib.resources import files
from pathlib import Path

from .download import cached_dictionary_path
from .extract import dictionary_entries
from .kaikki import (
    DictionaryFetchError,
    DictionaryWordNotFound,
    fetch_word_entries,
    kaikki_word_url,
)
from .models import (
    ContextCue,
    DictionaryEntry,
    DictionaryFetchResult,
    Example,
    Form,
    Pronunciation,
    Sense,
    TopicEvidence,
)
from .store import (
    LEGACY_SCHEMA_VERSION,
    OLDER_LEGACY_SCHEMA_VERSION,
    SCHEMA_VERSION,
    dictionary_coverage,
    initialize_partial,
    lookup_sense_count,
    lookup_status,
    metadata,
    migrate_partial_v3_to_v4,
    normalize_display_word,
    normalize_word,
    replace_word_entries,
)

_WORD_RE = re.compile(r"[^\W\d_]+(?:[-'][^\W\d_]+)*", re.UNICODE)


class DictionaryNotInstalled(FileNotFoundError):
    """Raised when a dictionary index is not locally available."""


class DictionaryIncompatible(RuntimeError):
    """Raised when a dictionary index does not match the runtime contract."""


class DictionaryOfflineError(DictionaryFetchError):
    """Raised when offline mode needs a word that is not cached."""


def _normalize(value: str) -> str:
    return normalize_word(value)


def _display_normalize(value: str) -> str:
    return normalize_display_word(value)


def _loads(value: str) -> object:
    return json.loads(value)


def _loads_tuple(value: str) -> tuple[str, ...]:
    data = _loads(value)
    return tuple(str(item) for item in data) if isinstance(data, list) else ()


def _loads_examples(value: str) -> tuple[Example, ...]:
    data = _loads(value)
    if not isinstance(data, list):
        return ()
    return tuple(
        Example(str(item["text"]), item.get("translation"))
        for item in data
        if isinstance(item, Mapping) and isinstance(item.get("text"), str)
    )


def _loads_forms(value: str) -> tuple[Form, ...]:
    data = _loads(value)
    if not isinstance(data, list):
        return ()
    return tuple(
        Form(str(item["form"]), tuple(str(tag) for tag in item.get("tags", ())))
        for item in data
        if isinstance(item, Mapping) and isinstance(item.get("form"), str)
    )


def _loads_pronunciations(value: str) -> tuple[Pronunciation, ...]:
    data = _loads(value)
    if not isinstance(data, list):
        return ()
    return tuple(
        Pronunciation(
            ipa=item.get("ipa") if isinstance(item.get("ipa"), str) else None,
            audio=item.get("audio") if isinstance(item.get("audio"), str) else None,
            tags=tuple(str(tag) for tag in item.get("tags", ())),
        )
        for item in data
        if isinstance(item, Mapping)
    )


def _runtime_metadata(path: Path) -> dict[str, str]:
    with closing(sqlite3.connect(path)) as connection:
        actual = metadata(connection)
    if actual.get("schema_version") in {LEGACY_SCHEMA_VERSION, OLDER_LEGACY_SCHEMA_VERSION}:
        if actual.get("coverage") == "partial":
            migrate_partial_v3_to_v4(path)
            with closing(sqlite3.connect(path)) as connection:
                actual = metadata(connection)
        elif actual.get("coverage") == "full":
            raise DictionaryIncompatible(
                f"schema {actual.get('schema_version')} full dictionary indexes are incomplete "
                "under schema 5; rebuild with 'lexhint dictionary build'"
            )
    return actual


def fetch_dictionary_word(
    language: str,
    word: str,
    *,
    path: str | Path | None = None,
    refresh: bool = False,
    offline: bool = False,
    timeout: float = 30.0,
) -> DictionaryFetchResult:
    """Fetch one exact Kaikki word page into a schema-v5 partial cache."""
    base_language = language.lower().split("-", 1)[0]
    query = _display_normalize(word)
    source_url = kaikki_word_url(query)
    target = Path(path).expanduser() if path is not None else cached_dictionary_path(base_language)
    if not target.exists():
        if offline:
            raise DictionaryOfflineError(f"dictionary data for {query!r} is not cached")
        initialize_partial(target, base_language)

    actual = _runtime_metadata(target)
    if actual.get("schema_version") != SCHEMA_VERSION:
        raise DictionaryIncompatible(
            f"dictionary index for {base_language!r} uses schema "
            f"{actual.get('schema_version', 'unknown')}; schema {SCHEMA_VERSION} is required"
        )
    if actual.get("language") != base_language:
        raise DictionaryIncompatible(
            f"dictionary index is for language {actual.get('language', 'unknown')!r}; "
            f"language {base_language!r} was requested"
        )

    if actual.get("coverage") == "full":
        return DictionaryFetchResult(
            query, "covered", lookup_sense_count(target, query), source_url, True
        )

    previous = lookup_status(target, query)
    if previous is not None and not refresh:
        return DictionaryFetchResult(
            query, "cached", lookup_sense_count(target, query), source_url, True
        )
    if offline:
        raise DictionaryOfflineError(f"dictionary data for {query!r} is not cached")

    try:
        raw_entries = fetch_word_entries(query, timeout=timeout)
    except DictionaryWordNotFound:
        replace_word_entries(
            target,
            language=base_language,
            query=query,
            source_url=source_url,
            entries=(),
            status="not_found",
        )
        return DictionaryFetchResult(query, "not_found", 0, source_url, False)

    entries = tuple(
        parsed
        for raw_entry in raw_entries
        for parsed in dictionary_entries(raw_entry, language=base_language)
    )
    senses = replace_word_entries(
        target,
        language=base_language,
        query=query,
        source_url=source_url,
        entries=entries,
    )
    return DictionaryFetchResult(query, "fetched", senses, source_url, False)


class Dictionary:
    """Read a curated rich dictionary index, optionally filling a partial cache."""

    def __init__(
        self,
        language: str,
        *,
        path: str | Path | None = None,
        fetch_missing: bool = False,
        offline: bool = False,
        timeout: float = 30.0,
    ) -> None:
        self.language = language.lower().split("-", 1)[0]
        self.path = Path(path).expanduser() if path is not None else self._resolve_path()
        self.fetch_missing = fetch_missing and not offline
        self.offline = offline
        self.timeout = timeout
        if not self.path.is_file():
            if offline:
                raise DictionaryOfflineError(f"dictionary data for {self.language!r} is not cached")
            if fetch_missing:
                initialize_partial(self.path, self.language)
            else:
                raise DictionaryNotInstalled(
                    f"no dictionary index installed for {self.language!r}; "
                    "run 'lexhint dictionary build ...' or 'lexhint dictionary fetch ...'"
                )
        self._validate_metadata()

    @classmethod
    def from_path(cls, path: str | Path, *, language: str | None = None) -> Dictionary:
        """Open an index, inferring its language unless one is asserted."""
        target = Path(path).expanduser()
        try:
            actual = _runtime_metadata(target)
        except (OSError, sqlite3.DatabaseError) as exc:
            raise DictionaryIncompatible("dictionary index has unreadable metadata") from exc
        stored_language = actual.get("language")
        if not stored_language:
            raise DictionaryIncompatible("dictionary index has no language metadata")
        selected_language = language or stored_language
        return cls(selected_language, path=target)

    def _resolve_path(self) -> Path:
        vendored = (
            files("lexhint")
            .joinpath("data")
            .joinpath("dictionaries")
            .joinpath(f"{self.language}.sqlite3")
        )
        try:
            if vendored.is_file():
                return Path(str(vendored))
        except TypeError:
            pass
        return cached_dictionary_path(self.language)

    def _connect(self) -> sqlite3.Connection:
        uri = self.path.resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    def _validate_metadata(self) -> None:
        try:
            actual = _runtime_metadata(self.path)
        except sqlite3.DatabaseError as exc:
            raise DictionaryIncompatible(
                f"dictionary index for {self.language!r} is not a valid lexhint index"
            ) from exc

        actual_schema = actual.get("schema_version")
        if actual_schema != SCHEMA_VERSION:
            raise DictionaryIncompatible(
                f"dictionary index for {self.language!r} uses schema "
                f"{actual_schema or 'unknown'}; schema {SCHEMA_VERSION} is required"
            )

        actual_language = actual.get("language")
        if actual_language != self.language:
            raise DictionaryIncompatible(
                f"dictionary index is for language {actual_language or 'unknown'!r}; "
                f"language {self.language!r} was requested"
            )
        if actual.get("coverage") not in {"partial", "full"}:
            raise DictionaryIncompatible("dictionary index has no valid coverage metadata")

    def _ensure_word(self, word: str, *, refresh: bool = False) -> None:
        if dictionary_coverage(self.path) == "full":
            return
        query = _display_normalize(word)
        if not refresh and lookup_status(self.path, query) is not None:
            return
        if self.offline:
            raise DictionaryOfflineError(f"dictionary data for {query!r} is not cached")
        if self.fetch_missing or refresh:
            fetch_dictionary_word(
                self.language,
                query,
                path=self.path,
                refresh=refresh,
                timeout=self.timeout,
            )

    def _entry_rows(self, word: str, *, all_case_variants: bool = False) -> list[sqlite3.Row]:
        normalized = _normalize(word)
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM entries WHERE word = ? ORDER BY id", (normalized,)
            ).fetchall()
        if not all_case_variants:
            display_word = _display_normalize(word)
            exact = [
                row for row in rows if _display_normalize(str(row["display_word"])) == display_word
            ]
            rows = exact or rows
        return rows

    def _entry(self, connection: sqlite3.Connection, row: sqlite3.Row) -> DictionaryEntry:
        senses = connection.execute(
            "SELECT glosses, topics, tags, examples, synonyms, antonyms "
            "FROM senses WHERE entry_id = ? ORDER BY sense_index",
            (row["id"],),
        ).fetchall()
        return DictionaryEntry(
            word=str(row["display_word"]),
            pos=str(row["pos"]),
            senses=tuple(
                Sense(
                    glosses=_loads_tuple(str(sense["glosses"])),
                    topics=_loads_tuple(str(sense["topics"])),
                    tags=_loads_tuple(str(sense["tags"])),
                    examples=_loads_examples(str(sense["examples"])),
                    synonyms=_loads_tuple(str(sense["synonyms"])),
                    antonyms=_loads_tuple(str(sense["antonyms"])),
                )
                for sense in senses
            ),
            forms=_loads_forms(str(row["forms"])),
            pronunciations=_loads_pronunciations(str(row["pronunciations"])),
            etymology=str(row["etymology"]) or None,
        )

    def lookup(
        self,
        word: str,
        *,
        all_case_variants: bool = False,
        refresh: bool = False,
    ) -> tuple[DictionaryEntry, ...]:
        """Return ordered rich entries for an exact word lookup."""
        self._ensure_word(word, refresh=refresh)
        rows = self._entry_rows(word, all_case_variants=all_case_variants)
        with closing(self._connect()) as connection:
            return tuple(self._entry(connection, row) for row in rows)

    def senses(
        self,
        word: str,
        *,
        all_case_variants: bool = False,
        refresh: bool = False,
    ) -> tuple[Sense, ...]:
        """Return the ordered senses derived from lookup()."""
        return tuple(
            sense
            for entry in self.lookup(word, all_case_variants=all_case_variants, refresh=refresh)
            for sense in entry.senses
        )

    def contains(self, word: str) -> bool:
        return bool(self.lookup(word))

    def topics(self, word: str) -> tuple[str, ...]:
        return tuple(sorted(self._topics_for_words((word,))[word]))

    def _topics_for_words(
        self, words: Iterable[str], *, refresh: bool = False
    ) -> dict[str, set[str]]:
        original_tokens = tuple(dict.fromkeys(word for word in words if word))
        for token in original_tokens:
            self._ensure_word(token, refresh=refresh)
        folded_keys = tuple(dict.fromkeys(_normalize(word) for word in original_tokens))
        if not folded_keys:
            return {}

        rows_by_folded: dict[str, list[sqlite3.Row]] = {word: [] for word in folded_keys}
        with closing(self._connect()) as connection:
            for offset in range(0, len(folded_keys), 500):
                chunk = folded_keys[offset : offset + 500]
                placeholders = ",".join("?" for _ in chunk)
                rows = connection.execute(
                    "SELECT e.word, e.display_word, st.topic "
                    "FROM entries AS e JOIN sense_topics AS st ON st.entry_id = e.id "
                    f"WHERE e.word IN ({placeholders})",  # noqa: S608
                    chunk,
                ).fetchall()
                for row in rows:
                    rows_by_folded[str(row["word"])].append(row)

        result: dict[str, set[str]] = {}
        for token in original_tokens:
            rows = rows_by_folded[_normalize(token)]
            display_word = _display_normalize(token)
            exact = [
                row for row in rows if _display_normalize(str(row["display_word"])) == display_word
            ]
            selected = exact or rows
            result[token] = {str(row["topic"]) for row in selected}
        return result

    @staticmethod
    def _target_indices(tokens: list[tuple[str, int, int]], target: tuple[int, int]) -> set[int]:
        start, end = target
        overlapping = {
            index
            for index, (_, token_start, token_end) in enumerate(tokens)
            if token_start < end and token_end > start
        }
        if overlapping:
            return overlapping
        center = (start + end) / 2
        nearest = min(
            range(len(tokens)),
            key=lambda index: abs(((tokens[index][1] + tokens[index][2]) / 2) - center),
        )
        return {nearest}

    def topic_scores(
        self,
        text: str,
        *,
        target: tuple[int, int],
        window: int = 6,
        decay: float = 0.7,
        limit: int | None = None,
        refresh: bool = False,
    ) -> tuple[TopicEvidence, ...]:
        """Aggregate nearby dictionary topics around a source span."""
        if window < 0:
            raise ValueError("window must be >= 0")
        if not 0.0 < decay <= 1.0:
            raise ValueError("decay must be in (0, 1]")
        start, end = target
        if not 0 <= start <= end <= len(text):
            raise ValueError("target must be a valid source span")

        tokens = [(m.group(0), m.start(), m.end()) for m in _WORD_RE.finditer(text)]
        if not tokens:
            return ()
        target_indices = self._target_indices(tokens, target)
        candidate_tokens = [
            token
            for index, (token, _, _) in enumerate(tokens)
            if index not in target_indices
            and min(abs(index - target_index) for target_index in target_indices) <= window
        ]
        topics_by_word = self._topics_for_words(candidate_tokens, refresh=refresh)

        scores: dict[str, float] = {}
        cues: dict[str, list[ContextCue]] = {}
        for index, (token, token_start, token_end) in enumerate(tokens):
            if index in target_indices:
                continue
            distance = min(abs(index - target_index) for target_index in target_indices)
            if distance > window:
                continue
            for topic in topics_by_word.get(token, ()):
                key = _normalize(topic)
                weight = decay**distance
                scores[key] = scores.get(key, 0.0) + weight
                cues.setdefault(key, []).append(
                    ContextCue(token, token_start, token_end, distance, weight)
                )

        ranked = [
            TopicEvidence(topic, score, tuple(cues[topic])) for topic, score in scores.items()
        ]
        ranked.sort(key=lambda item: (-item.score, item.topic))
        if limit is not None:
            if limit < 0:
                raise ValueError("limit must be >= 0")
            ranked = ranked[:limit]
        return tuple(ranked)

    def supports(
        self,
        text: str,
        *,
        target: tuple[int, int],
        topic: str,
        window: int = 6,
        decay: float = 0.7,
        threshold: float = 0.4,
        refresh: bool = False,
    ) -> TopicEvidence | None:
        """Return nearby soft dictionary evidence for a requested topic."""
        wanted = _normalize(topic)
        for score in self.topic_scores(
            text,
            target=target,
            window=window,
            decay=decay,
            limit=None,
            refresh=refresh,
        ):
            if _normalize(score.topic) == wanted and score.score >= threshold:
                return score
        return None


__all__ = [
    "Dictionary",
    "DictionaryFetchError",
    "DictionaryIncompatible",
    "DictionaryNotInstalled",
    "DictionaryOfflineError",
    "DictionaryWordNotFound",
    "fetch_dictionary_word",
]
