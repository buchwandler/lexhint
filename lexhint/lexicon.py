from __future__ import annotations

import json
import math
import re
import sqlite3
from collections.abc import Mapping
from contextlib import closing
from importlib.resources import files
from pathlib import Path

from .download import cached_dictionary_path
from .models import (
    ContextCue,
    DictionaryEntry,
    DomainEvidence,
    Example,
    Form,
    LexicalSegment,
    Pronunciation,
    SemanticDomain,
    Sense,
    TopicEvidence,
    WordEvidence,
)
from .store import SCHEMA_VERSION, normalize_display_word, normalize_word

_WORD_RE = re.compile(r"[^\W\d_]+(?:[-'][^\W\d_]+)*", re.UNICODE)


class LexiconNotInstalled(FileNotFoundError):
    """The requested local language artifact does not exist."""


class LexiconIncompatible(RuntimeError):
    """The local artifact does not satisfy the Lexhint schema contract."""


class LexiconCapabilityError(RuntimeError):
    """The artifact does not contain data required by an operation."""


class LexiconCoverageError(RuntimeError):
    """The artifact does not have authoritative full lexical coverage."""


class Lexicon:
    """Read-only lexical evidence from one self-describing SQLite artifact."""

    def __init__(
        self,
        language: str,
        *,
        path: str | Path | None = None,
    ) -> None:
        self.language = language.lower().split("-", 1)[0]
        self.path = Path(path).expanduser() if path is not None else self._resolve_path()
        if not self.path.is_file():
            raise LexiconNotInstalled(
                f"no local lexicon artifact installed for {self.language!r}; "
                "build or install a Lexhint SQLite database"
            )
        self._metadata = self._read_metadata()
        self._validate_metadata()

    @classmethod
    def from_path(cls, path: str | Path, *, language: str | None = None) -> Lexicon:
        target = Path(path).expanduser()
        try:
            with closing(sqlite3.connect(target)) as connection:
                connection.row_factory = sqlite3.Row
                actual = {
                    str(row["key"]): str(row["value"])
                    for row in connection.execute("SELECT key, value FROM metadata")
                }
        except (OSError, sqlite3.DatabaseError) as exc:
            raise LexiconIncompatible("lexicon artifact has unreadable metadata") from exc
        stored = actual.get("language")
        if not stored:
            raise LexiconIncompatible("lexicon artifact has no language metadata")
        return cls(language or stored, path=target)

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

    def _read_metadata(self) -> dict[str, str]:
        try:
            with closing(sqlite3.connect(self.path)) as connection:
                return {
                    str(row[0]): str(row[1])
                    for row in connection.execute("SELECT key, value FROM metadata")
                }
        except (OSError, sqlite3.DatabaseError) as exc:
            raise LexiconIncompatible("lexicon artifact has unreadable metadata") from exc

    def _validate_metadata(self) -> None:
        schema = self._metadata.get("schema_version")
        if schema != SCHEMA_VERSION:
            raise LexiconIncompatible(
                f"lexicon for {self.language!r} uses schema {schema or 'unknown'}; "
                f"schema {SCHEMA_VERSION} is required; rebuild the artifact"
            )
        if self._metadata.get("language") != self.language:
            raise LexiconIncompatible(
                f"lexicon is for language {self._metadata.get('language', 'unknown')!r}; "
                f"language {self.language!r} was requested"
            )
        if self._metadata.get("coverage") not in {"full", "partial"}:
            raise LexiconIncompatible("lexicon has no valid coverage metadata")
        capabilities = self._metadata.get("capabilities", "")
        if "lexical" not in {item for item in capabilities.split(",") if item}:
            raise LexiconIncompatible("lexicon metadata does not declare lexical capability")

    @property
    def metadata(self) -> Mapping[str, str]:
        return dict(self._metadata)

    @property
    def capabilities(self) -> tuple[str, ...]:
        return tuple(item for item in self._metadata.get("capabilities", "").split(",") if item)

    @property
    def has_frequency_data(self) -> bool:
        return (
            bool(self._metadata.get("frequency_source"))
            and self._metadata.get("frequency_source") != "none"
        )

    def _connect(self) -> sqlite3.Connection:
        uri = self.path.resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    def _require(self, capability: str) -> None:
        if capability not in self.capabilities:
            raise LexiconCapabilityError(
                f"Lexicon capability {capability!r} is not available in this artifact"
            )

    def _require_full(self) -> None:
        if self._metadata.get("coverage") != "full":
            raise LexiconCoverageError(
                "operation requires an artifact with authoritative full lexical coverage"
            )

    def word(self, word: str) -> WordEvidence:
        self._require("lexical")
        normalized = normalize_word(word)
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT corpus_count, corpus_rank FROM lexemes WHERE word=?", (normalized,)
            ).fetchone()
        if row is None:
            return WordEvidence(word, False)
        return WordEvidence(word, True, row["corpus_rank"], row["corpus_count"])

    def word_info(self, word: str) -> WordEvidence:
        return self.word(word)

    def contains(self, word: str) -> bool:
        return self.word(word).known

    def _lexeme_candidates(self, values: set[str]) -> dict[str, sqlite3.Row]:
        result: dict[str, sqlite3.Row] = {}
        candidates = tuple(values)
        with closing(self._connect()) as connection:
            for offset in range(0, len(candidates), 500):
                chunk = candidates[offset : offset + 500]
                placeholders = ",".join("?" for _ in chunk)
                rows = connection.execute(
                    "SELECT word, corpus_count, corpus_rank, has_lowercase, has_titlecase, "
                    "has_uppercase FROM lexemes WHERE word IN (" + placeholders + ")",
                    chunk,
                ).fetchall()
                result.update({str(row["word"]): row for row in rows})
        return result

    def segment(self, text: str, *, max_word_length: int = 32) -> tuple[LexicalSegment, ...]:
        self._require("lexical")
        self._require_full()
        value = normalize_word(text)
        if not value:
            return ()
        candidates = {
            value[start:end]
            for end in range(1, len(value) + 1)
            for start in range(max(0, end - max_word_length), end)
        }
        lexemes = self._lexeme_candidates(candidates)
        n = len(value)
        best = [-math.inf] * (n + 1)
        previous: list[tuple[int, bool, int | None] | None] = [None] * (n + 1)
        best[0] = 0.0
        for end in range(1, n + 1):
            unknown_score = best[end - 1] - 5.0
            if unknown_score > best[end]:
                best[end] = unknown_score
                previous[end] = (end - 1, False, None)
            for start in range(max(0, end - max_word_length), end):
                info = lexemes.get(value[start:end])
                if info is None:
                    continue
                length = end - start
                rank = info["corpus_rank"]
                if length == 2 and (rank is None or rank > 2_000):
                    continue
                if value.islower() and not info["has_lowercase"]:
                    continue
                frequency_penalty = math.log10(rank + 9) if rank is not None else 7.0
                score = best[start] + length * 6.0 - frequency_penalty
                if score > best[end]:
                    best[end] = score
                    previous[end] = (start, True, rank)
        raw: list[LexicalSegment] = []
        cursor = n
        while cursor > 0:
            start, known, rank = previous[cursor] or (cursor - 1, False, None)
            raw.append(LexicalSegment(value[start:cursor], known, rank))
            cursor = start
        raw.reverse()
        merged: list[LexicalSegment] = []
        for item in raw:
            if not item.known and merged and not merged[-1].known:
                merged[-1] = LexicalSegment(merged[-1].text + item.text, False)
            else:
                merged.append(item)
        return tuple(merged)

    @staticmethod
    def _loads(value: str) -> object:
        return json.loads(value)

    @classmethod
    def _tuple(cls, value: str) -> tuple[str, ...]:
        data = cls._loads(value)
        return tuple(str(item) for item in data) if isinstance(data, list) else ()

    @classmethod
    def _entry(cls, connection: sqlite3.Connection, row: sqlite3.Row) -> DictionaryEntry:
        def examples(value: str) -> tuple[Example, ...]:
            data = cls._loads(value)
            return (
                tuple(
                    Example(str(item["text"]), item.get("translation"))
                    for item in data
                    if isinstance(item, Mapping) and isinstance(item.get("text"), str)
                )
                if isinstance(data, list)
                else ()
            )

        def forms(value: str) -> tuple[Form, ...]:
            data = cls._loads(value)
            return (
                tuple(
                    Form(str(item["form"]), tuple(str(tag) for tag in item.get("tags", ())))
                    for item in data
                    if isinstance(item, Mapping) and isinstance(item.get("form"), str)
                )
                if isinstance(data, list)
                else ()
            )

        def pronunciations(value: str) -> tuple[Pronunciation, ...]:
            data = cls._loads(value)
            return (
                tuple(
                    Pronunciation(str(item["ipa"]), tuple(str(tag) for tag in item.get("tags", ())))
                    for item in data
                    if isinstance(item, Mapping) and isinstance(item.get("ipa"), str)
                )
                if isinstance(data, list)
                else ()
            )

        senses = connection.execute(
            "SELECT glosses, topics, tags, examples, synonyms, antonyms FROM senses "
            "WHERE entry_id=? ORDER BY sense_index",
            (row["id"],),
        ).fetchall()
        return DictionaryEntry(
            word=str(row["display_word"]),
            pos=str(row["pos"]),
            senses=tuple(
                Sense(
                    cls._tuple(str(sense["glosses"])),
                    cls._tuple(str(sense["topics"])),
                    cls._tuple(str(sense["tags"])),
                    examples(str(sense["examples"])),
                    cls._tuple(str(sense["synonyms"])),
                    cls._tuple(str(sense["antonyms"])),
                )
                for sense in senses
            ),
            forms=forms(str(row["forms"])),
            pronunciations=pronunciations(str(row["pronunciations"])),
            etymology=str(row["etymology"]) or None,
        )

    def entries(self, word: str, *, all_case_variants: bool = False) -> tuple[DictionaryEntry, ...]:
        self._require("dictionary")
        normalized = normalize_word(word)
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM entries WHERE word=? ORDER BY id", (normalized,)
            ).fetchall()
            if not all_case_variants:
                wanted = normalize_display_word(word)
                exact = [
                    row for row in rows if normalize_display_word(row["display_word"]) == wanted
                ]
                rows = exact or rows
            return tuple(self._entry(connection, row) for row in rows)

    def lookup(
        self, word: str, *, all_case_variants: bool = False, refresh: bool = False
    ) -> tuple[DictionaryEntry, ...]:
        del refresh
        return self.entries(word, all_case_variants=all_case_variants)

    def senses(
        self, word: str, *, all_case_variants: bool = False, refresh: bool = False
    ) -> tuple[Sense, ...]:
        return tuple(
            sense
            for entry in self.lookup(word, all_case_variants=all_case_variants, refresh=refresh)
            for sense in entry.senses
        )

    def topics(self, word: str) -> tuple[str, ...]:
        self._require("dictionary")
        return tuple(sorted({topic for sense in self.senses(word) for topic in sense.topics}))

    @staticmethod
    def _target_indices(tokens: list[tuple[str, int, int]], target: tuple[int, int]) -> set[int]:
        start, end = target
        overlapping = {
            i
            for i, (_, token_start, token_end) in enumerate(tokens)
            if token_start < end and token_end > start
        }
        if overlapping:
            return overlapping
        if not tokens:
            return set()
        center = (start + end) / 2
        return {
            min(range(len(tokens)), key=lambda i: abs((tokens[i][1] + tokens[i][2]) / 2 - center))
        }

    def context_domains(
        self,
        text: str,
        *,
        target: tuple[int, int],
        window: int = 6,
        decay: float = 0.7,
        limit: int | None = None,
    ) -> tuple[DomainEvidence, ...]:
        self._require("semantic")
        self._require_full()
        if window < 0:
            raise ValueError("window must be >= 0")
        if not 0.0 < decay <= 1.0:
            raise ValueError("decay must be in (0, 1]")
        start, end = target
        if not 0 <= start <= end <= len(text):
            raise ValueError("target must be a valid source span")
        tokens = [(match.group(0), match.start(), match.end()) for match in _WORD_RE.finditer(text)]
        target_indices = self._target_indices(tokens, target)
        if not tokens:
            return ()
        candidate_indices = [
            i
            for i in range(len(tokens))
            if i not in target_indices
            and min(abs(i - target_i) for target_i in target_indices) <= window
        ]
        words = tuple(dict.fromkeys(normalize_word(tokens[i][0]) for i in candidate_indices))
        rows: dict[str, list[sqlite3.Row]] = {word: [] for word in words}
        with closing(self._connect()) as connection:
            for offset in range(0, len(words), 500):
                chunk = words[offset : offset + 500]
                if not chunk:
                    continue
                placeholders = ",".join("?" for _ in chunk)
                result = connection.execute(
                    "SELECT word, domain, weight FROM lexeme_domains WHERE word IN ("
                    + placeholders
                    + ")",
                    chunk,
                ).fetchall()
                for row in result:
                    rows[str(row["word"])].append(row)
        scores: dict[SemanticDomain, float] = {}
        cues: dict[SemanticDomain, list[ContextCue]] = {}
        for index in candidate_indices:
            token, token_start, token_end = tokens[index]
            distance = min(abs(index - target_i) for target_i in target_indices)
            for row in rows.get(normalize_word(token), ()):
                try:
                    domain = SemanticDomain(str(row["domain"]))
                except ValueError:
                    continue
                weight = float(row["weight"]) * decay**distance
                scores[domain] = scores.get(domain, 0.0) + weight
                cues.setdefault(domain, []).append(
                    ContextCue(token, token_start, token_end, distance, weight)
                )
        ranked = [
            DomainEvidence(domain, score, tuple(cues[domain])) for domain, score in scores.items()
        ]
        ranked.sort(key=lambda item: (-item.score, item.domain.value))
        if limit is not None:
            if limit < 0:
                raise ValueError("limit must be >= 0")
            ranked = ranked[:limit]
        return tuple(ranked)

    def supports_domain(
        self,
        text: str,
        *,
        target: tuple[int, int],
        domain: SemanticDomain | str,
        window: int = 6,
        decay: float = 0.7,
        threshold: float = 0.4,
    ) -> DomainEvidence | None:
        wanted = domain if isinstance(domain, SemanticDomain) else SemanticDomain(str(domain))
        return next(
            (
                item
                for item in self.context_domains(text, target=target, window=window, decay=decay)
                if item.domain == wanted and item.score >= threshold
            ),
            None,
        )

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
        del refresh
        self._require("dictionary")
        tokens = [(m.group(0), m.start(), m.end()) for m in _WORD_RE.finditer(text)]
        target_indices = self._target_indices(tokens, target)
        scores: dict[str, float] = {}
        cues: dict[str, list[ContextCue]] = {}
        for i, (token, start, end) in enumerate(tokens):
            if i in target_indices:
                continue
            distance = min(abs(i - target_i) for target_i in target_indices)
            if distance > window:
                continue
            for topic in self.topics(token):
                weight = decay**distance
                scores[topic] = scores.get(topic, 0.0) + weight
                cues.setdefault(topic, []).append(ContextCue(token, start, end, distance, weight))
        ranked = [
            TopicEvidence(topic, score, tuple(cues[topic])) for topic, score in scores.items()
        ]
        ranked.sort(key=lambda item: (-item.score, item.topic))
        return tuple(ranked[:limit] if limit is not None else ranked)

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
        wanted = normalize_word(topic)
        return next(
            (
                item
                for item in self.topic_scores(
                    text, target=target, window=window, decay=decay, refresh=refresh
                )
                if normalize_word(item.topic) == wanted and item.score >= threshold
            ),
            None,
        )


__all__ = [
    "Lexicon",
    "LexiconCapabilityError",
    "LexiconCoverageError",
    "LexiconIncompatible",
    "LexiconNotInstalled",
]
