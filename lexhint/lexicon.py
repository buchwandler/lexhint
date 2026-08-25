from __future__ import annotations

import fnmatch
import json
import math
import os
import re
import sqlite3
from collections.abc import Callable, Mapping
from contextlib import closing
from dataclasses import replace
from importlib.resources import files
from pathlib import Path

from .download import cached_dictionary_path
from .languages import is_regional_source_tag, locale_spec, normalize_language, normalize_locale
from .models import (
    ContextCue,
    DictionaryEntry,
    DictionarySearchHit,
    DomainEvidence,
    Example,
    ExternalSenseId,
    Form,
    HeadwordRelation,
    LexicalSegment,
    Pronunciation,
    RelatedTerm,
    SemanticDomain,
    Sense,
    SenseRecord,
    WordEvidence,
)
from .schema_contract import SchemaContractError, validate_artifact_structure
from .search import (
    FIELD_WEIGHTS,
    capped_term_frequency,
    edit_distance,
    glob_literal_prefix,
    regex_literal_prefix,
    search_tokens,
    word_ngrams,
)
from .store import (
    SCHEMA_VERSION,
    format_sense_id,
    normalize_display_word,
    normalize_word,
    parse_sense_id,
)

_WORD_RE = re.compile(r"[^\W\d_]+(?:[-'][^\W\d_]+)*", re.UNICODE)


class LexiconNotInstalled(FileNotFoundError):
    """The requested local language artifact does not exist."""


class LexiconIncompatible(RuntimeError):
    """The local artifact does not satisfy the Lexhint schema contract."""


class LexiconCapabilityError(RuntimeError):
    """The artifact does not contain data required by an operation."""


class LexiconCoverageError(RuntimeError):
    """The artifact does not have authoritative full lexical coverage."""


def _locale_rank(tags: tuple[str, ...], locale: str | None) -> int:
    if locale is None:
        return 0
    spec = locale_spec("en", locale)
    assert spec is not None
    normalized = {tag.casefold() for tag in tags}
    preferred = {tag.casefold() for tag in spec.preferred_source_tags}
    if normalized & preferred:
        return 0
    if any(is_regional_source_tag(tag) for tag in tags):
        return 2
    return 1


def _prefix_upper_bound(prefix: str) -> str | None:
    """Return the exclusive upper bound for strings beginning with *prefix*."""
    for index in range(len(prefix) - 1, -1, -1):
        codepoint = ord(prefix[index])
        if codepoint >= 0x10FFFF:
            continue
        next_codepoint = codepoint + 1
        if 0xD800 <= next_codepoint <= 0xDFFF:
            next_codepoint = 0xE000
        return prefix[:index] + chr(next_codepoint)
    return None


class Lexicon:
    """Read-only lexical evidence from one self-describing SQLite artifact."""

    def __init__(
        self,
        language: str,
        *,
        variant: str | None = None,
        dataset_version: str | None = None,
        path: str | Path | None = None,
        locale: str | None = None,
    ) -> None:
        if path is not None and (variant is not None or dataset_version is not None):
            raise ValueError("path cannot be combined with variant or dataset_version")
        self.language = normalize_language(language)
        self.locale = normalize_locale(self.language, locale)
        self.variant = variant
        self.dataset_version = dataset_version
        self.path = Path(path).expanduser() if path is not None else self._resolve_path()
        if not self.path.is_file():
            if path is not None:
                raise LexiconNotInstalled(
                    f"no local lexicon artifact at {self.path}; "
                    "build or install a Lexhint SQLite database"
                )
            raise LexiconNotInstalled(
                f"no local lexicon artifact installed for {self.language!r}; "
                f"run 'lexhint dataset download {self.language}'"
            )
        self._metadata = self._read_metadata()
        self._validate_metadata()

    @staticmethod
    def _connect_path_readonly(path: Path) -> sqlite3.Connection:
        uri = path.resolve().as_uri() + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    @classmethod
    def from_path(
        cls, path: str | Path, *, language: str | None = None, locale: str | None = None
    ) -> Lexicon:
        target = Path(path).expanduser()
        if not target.is_file():
            raise LexiconNotInstalled(
                f"no local lexicon artifact at {target}; build or install a Lexhint SQLite database"
            )
        try:
            with closing(cls._connect_path_readonly(target)) as connection:
                actual = {
                    str(row["key"]): str(row["value"])
                    for row in connection.execute("SELECT key, value FROM metadata")
                }
        except (OSError, sqlite3.DatabaseError) as exc:
            raise LexiconIncompatible("lexicon artifact has unreadable metadata") from exc
        stored = actual.get("language")
        if not stored:
            raise LexiconIncompatible("lexicon artifact has no language metadata")
        return cls(language or stored, locale=locale, path=target)

    def _resolve_path(self) -> Path:
        from .datasets import DatasetAmbiguous, DatasetError, resolve_installed_dataset

        if self.variant is not None or self.dataset_version is not None:
            try:
                return resolve_installed_dataset(
                    self.language, variant=self.variant, version=self.dataset_version
                ).path
            except DatasetAmbiguous:
                raise
            except DatasetError as exc:
                raise LexiconNotInstalled(str(exc)) from exc

        def installed_path() -> Path | None:
            try:
                return resolve_installed_dataset(self.language).path
            except DatasetAmbiguous:
                raise
            except DatasetError:
                return None

        if os.environ.get("LEXHINT_DATA_DIR"):
            installed = installed_path()
            if installed is not None:
                return installed

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
        cached = cached_dictionary_path(self.language)
        if cached.is_file():
            return cached
        installed = installed_path()
        if installed is not None:
            return installed
        return cached

    def _read_metadata(self) -> dict[str, str]:
        try:
            with closing(self._connect_path_readonly(self.path)) as connection:
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
        try:
            with closing(self._connect()) as connection:
                validate_artifact_structure(
                    connection, (item for item in capabilities.split(",") if item)
                )
        except (OSError, sqlite3.DatabaseError, SchemaContractError) as exc:
            raise LexiconIncompatible(
                f"lexicon structure does not satisfy schema {SCHEMA_VERSION}: {exc}"
            ) from exc

    @property
    def schema_version(self) -> str:
        return SCHEMA_VERSION

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
        return self._connect_path_readonly(self.path)

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
                "SELECT corpus_count, corpus_rank, has_lowercase, has_titlecase, "
                "has_uppercase FROM lexemes WHERE word=?",
                (normalized,),
            ).fetchone()
        if row is None:
            return WordEvidence(word, False)
        return WordEvidence(
            text=word,
            known=True,
            frequency_rank=row["corpus_rank"],
            frequency_count=row["corpus_count"],
            has_lowercase=bool(row["has_lowercase"]),
            has_titlecase=bool(row["has_titlecase"]),
            has_uppercase=bool(row["has_uppercase"]),
        )

    def contains(self, word: str) -> bool:
        return self.word(word).known

    def complete(self, prefix: str, *, limit: int = 20) -> tuple[str, ...]:
        """Return deterministic normalized lexical-key completions for *prefix*.

        Matching uses the same NFC + casefold normalization as lexical membership.
        An exact normalized key is returned first. Remaining results begin with the
        full normalized prefix and are ranked by corpus commonness when frequency
        data is available, with deterministic lexical fallback ordering.

        This operation is local, read-only, and is not spelling correction.
        """
        self._require("lexical")
        if limit < 0:
            raise ValueError("limit must be >= 0")
        normalized = normalize_word(prefix.strip())
        if not normalized or limit == 0:
            return ()

        upper = _prefix_upper_bound(normalized)
        with closing(self._connect()) as connection:
            exact = connection.execute(
                "SELECT word FROM lexemes WHERE word=?",
                (normalized,),
            ).fetchone()

            result: list[str] = []
            if exact is not None:
                result.append(str(exact["word"]))
                if len(result) == limit:
                    return tuple(result)

            if upper is None:
                return tuple(result)

            remaining = limit - len(result)
            if self.has_frequency_data:
                rows = connection.execute(
                    "SELECT word FROM lexemes "
                    "WHERE word >= ? AND word < ? AND word != ? "
                    "ORDER BY corpus_rank IS NULL, corpus_rank, word LIMIT ?",
                    (normalized, upper, normalized, remaining),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT word FROM lexemes "
                    "WHERE word >= ? AND word < ? AND word != ? "
                    "ORDER BY word LIMIT ?",
                    (normalized, upper, normalized, remaining),
                ).fetchall()

        result.extend(str(row["word"]) for row in rows)
        return tuple(result)

    def suggest(
        self,
        query: str,
        *,
        limit: int = 20,
        max_distance: int | None = None,
    ) -> tuple[str, ...]:
        """Return bounded, deterministic fuzzy spelling candidates."""
        self._require("lexical")
        self._require("search")
        if limit < 0:
            raise ValueError("limit must be >= 0")
        if max_distance is not None and max_distance < 0:
            raise ValueError("max_distance must be >= 0")
        normalized = normalize_word(query.strip())
        if not normalized or limit == 0:
            return ()
        if max_distance is None:
            max_distance = 1 if len(normalized) <= 5 else 2
        grams = tuple(sorted(word_ngrams(normalized)))
        if not grams:
            return ()
        candidate_pool = max(200, limit * 50)
        placeholders = ", ".join("?" for _ in grams)
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT n.word, l.corpus_rank, COUNT(*) AS overlap "
                "FROM lexeme_ngrams AS n JOIN lexemes AS l ON l.word=n.word "
                f"WHERE n.gram IN ({placeholders}) "
                "GROUP BY n.word ORDER BY overlap DESC, n.word LIMIT ?",
                (*grams, candidate_pool),
            ).fetchall()
        ranked: list[tuple[tuple[object, ...], str]] = []
        for row in rows:
            word = str(row["word"])
            distance = edit_distance(normalized, word, max_distance=max_distance)
            if distance > max_distance:
                continue
            rank = row["corpus_rank"]
            key = (
                distance,
                rank is None,
                rank if rank is not None else 10**18,
                word,
            )
            ranked.append((key, word))
        ranked.sort(key=lambda item: item[0])
        return tuple(word for _, word in ranked[:limit])

    def match_headwords(
        self,
        pattern: str,
        *,
        syntax: str = "glob",
        limit: int = 100,
    ) -> tuple[str, ...]:
        """Match normalized lexical keys with glob or full-match regex syntax."""
        self._require("lexical")
        if limit < 0:
            raise ValueError("limit must be >= 0")
        if limit == 0:
            return ()
        if syntax not in {"glob", "regex"}:
            raise ValueError("syntax must be 'glob' or 'regex'")
        normalized_pattern = normalize_word(pattern)
        if syntax == "glob":

            def glob_match(word: str) -> bool:
                return fnmatch.fnmatchcase(word, normalized_pattern)

            matcher: Callable[[str], bool] = glob_match
            prefix = glob_literal_prefix(normalized_pattern)
        else:
            try:
                compiled = re.compile(normalized_pattern)
            except re.error as exc:
                raise ValueError(f"invalid regex pattern: {exc}") from exc

            def regex_match(word: str) -> bool:
                return compiled.fullmatch(word) is not None

            matcher = regex_match
            prefix = regex_literal_prefix(normalized_pattern)
        upper = _prefix_upper_bound(prefix) if prefix else None
        query = "SELECT word FROM lexemes"
        parameters: tuple[object, ...] = ()
        if prefix and upper is not None:
            query += " WHERE word >= ? AND word < ?"
            parameters = (prefix, upper)
        query += " ORDER BY word"
        matches: list[str] = []
        with closing(self._connect()) as connection:
            cursor = connection.execute(query, parameters)
            while len(matches) < limit:
                rows = cursor.fetchmany(256)
                if not rows:
                    break
                for row in rows:
                    word = str(row["word"])
                    if matcher(word):
                        matches.append(word)
                        if len(matches) == limit:
                            break
        return tuple(matches)

    def search_definitions(
        self,
        query: str,
        *,
        fields: tuple[str, ...] = ("glosses",),
        match: str = "all",
        limit: int = 50,
    ) -> tuple[DictionarySearchHit, ...]:
        """Search indexed dictionary sense text with deterministic relevance."""
        self._require("dictionary")
        self._require("search")
        if limit < 0:
            raise ValueError("limit must be >= 0")
        if match not in {"all", "any"}:
            raise ValueError("match must be 'all' or 'any'")
        allowed = set(FIELD_WEIGHTS)
        selected_fields = tuple(dict.fromkeys(fields))
        unknown = sorted(set(selected_fields) - allowed)
        if unknown:
            raise ValueError(f"unknown search field {unknown[0]!r}")
        if not selected_fields:
            raise ValueError("fields must not be empty")
        if limit == 0:
            return ()
        terms = tuple(dict.fromkeys(search_tokens(query)))
        if not terms:
            return ()
        term_placeholders = ", ".join("?" for _ in terms)
        field_placeholders = ", ".join("?" for _ in selected_fields)
        sql = (
            "SELECT t.sense_id, t.term, t.field, t.term_count, "
            "s.glosses, s.sense_index, e.display_word, e.pos, e.entry_index, "
            "l.corpus_rank "
            "FROM sense_search_terms AS t "
            "JOIN senses AS s ON s.id=t.sense_id "
            "JOIN entries AS e ON e.id=s.entry_id "
            "LEFT JOIN lexemes AS l ON l.word=e.word "
            f"WHERE t.term IN ({term_placeholders}) "
            f"AND t.field IN ({field_placeholders})"
        )
        parameters = (*terms, *selected_fields)
        grouped: dict[int, list[sqlite3.Row]] = {}
        with closing(self._connect()) as connection:
            for row in connection.execute(sql, parameters):
                grouped.setdefault(int(row["sense_id"]), []).append(row)
        ranked: list[tuple[tuple[object, ...], DictionarySearchHit]] = []
        for rows in grouped.values():
            first = rows[0]
            term_fields: dict[str, dict[str, int]] = {}
            for row in rows:
                term_fields.setdefault(str(row["term"]), {})[str(row["field"])] = int(
                    row["term_count"]
                )
            matched_terms = tuple(term for term in terms if term in term_fields)
            if match == "all" and len(matched_terms) != len(terms):
                continue
            matched_fields = tuple(
                field
                for field in selected_fields
                if any(field in term_fields[term] for term in matched_terms)
            )
            score = sum(
                FIELD_WEIGHTS[field] * capped_term_frequency(count)
                for term in matched_terms
                for field, count in term_fields[term].items()
            )
            hit = DictionarySearchHit(
                word=str(first["display_word"]),
                pos=str(first["pos"]),
                sense_index=int(first["sense_index"]),
                glosses=self._tuple(str(first["glosses"])),
                score=float(score),
                matched_terms=matched_terms,
                matched_fields=matched_fields,
            )
            rank = first["corpus_rank"]
            key = (
                -score,
                rank is None,
                rank if rank is not None else 10**18,
                hit.word.casefold(),
                int(first["entry_index"]),
                hit.sense_index,
            )
            ranked.append((key, hit))
        ranked.sort(key=lambda item: item[0])
        return tuple(hit for _, hit in ranked[:limit])

    def reverse(self, query: str, *, limit: int = 50) -> tuple[DictionarySearchHit, ...]:
        """Search glosses using reverse-dictionary semantics."""
        return self.search_definitions(query, fields=("glosses",), match="all", limit=limit)

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
        if not normalize_word(text):
            return ()
        candidates = {
            normalize_word(text[start:end])
            for end in range(1, len(text) + 1)
            for start in range(max(0, end - max_word_length), end)
        }
        lexemes = self._lexeme_candidates(candidates)
        n = len(text)
        best = [-math.inf] * (n + 1)
        previous: list[tuple[int, bool, int | None] | None] = [None] * (n + 1)
        best[0] = 0.0
        for end in range(1, n + 1):
            unknown_score = best[end - 1] - 5.0
            if unknown_score > best[end]:
                best[end] = unknown_score
                previous[end] = (end - 1, False, None)
            for start in range(max(0, end - max_word_length), end):
                info = lexemes.get(normalize_word(text[start:end]))
                if info is None:
                    continue
                candidate = text[start:end]
                length = end - start
                rank = info["corpus_rank"]
                if length == 2 and (rank is None or rank > 2_000):
                    continue
                if candidate.islower() and not info["has_lowercase"]:
                    continue
                if candidate.istitle() and not info["has_titlecase"]:
                    continue
                if candidate.isupper() and not info["has_uppercase"]:
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
            raw.append(LexicalSegment(text[start:cursor], known, rank))
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
    def _related(cls, value: str) -> tuple[str | RelatedTerm, ...]:
        data = cls._loads(value)
        if not isinstance(data, list):
            return ()
        result: list[str | RelatedTerm] = []
        for item in data:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, Mapping) and isinstance(item.get("word"), str):
                result.append(
                    RelatedTerm(
                        str(item["word"]),
                        str(item.get("relation", "")),
                        tuple(str(tag) for tag in item.get("tags", ())),
                    )
                )
        return tuple(result)

    def _entry(self, connection: sqlite3.Connection, row: sqlite3.Row) -> DictionaryEntry:
        def examples(value: str) -> tuple[Example, ...]:
            data = self._loads(value)
            return (
                tuple(
                    Example(
                        str(item["text"]),
                        item.get("translation"),
                        item.get("kind") or item.get("type"),
                    )
                    for item in data
                    if isinstance(item, Mapping) and isinstance(item.get("text"), str)
                )
                if isinstance(data, list)
                else ()
            )

        def forms(value: str) -> tuple[Form, ...]:
            data = self._loads(value)
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
            data = self._loads(value)
            return (
                tuple(
                    Pronunciation(str(item["ipa"]), tuple(str(tag) for tag in item.get("tags", ())))
                    for item in data
                    if isinstance(item, Mapping) and isinstance(item.get("ipa"), str)
                )
                if isinstance(data, list)
                else ()
            )

        def source_ids(value: str) -> tuple[ExternalSenseId, ...]:
            data = self._loads(value)
            return (
                tuple(
                    ExternalSenseId(str(item["namespace"]), str(item["value"]))
                    for item in data
                    if isinstance(item, Mapping)
                    and isinstance(item.get("namespace"), str)
                    and isinstance(item.get("value"), str)
                )
                if isinstance(data, list)
                else ()
            )

        senses = connection.execute(
            "SELECT id, glosses, topics, tags, examples, synonyms, antonyms, source_ids "
            "FROM senses WHERE entry_id=? ORDER BY sense_index",
            (row["id"],),
        ).fetchall()
        return DictionaryEntry(
            word=str(row["display_word"]),
            pos=str(row["pos"]),
            senses=tuple(
                Sense(
                    glosses=self._tuple(str(sense["glosses"])),
                    topics=self._tuple(str(sense["topics"])),
                    tags=self._tuple(str(sense["tags"])),
                    examples=examples(str(sense["examples"])),
                    synonyms=self._related(str(sense["synonyms"])),
                    antonyms=self._related(str(sense["antonyms"])),
                    sense_id=format_sense_id(self.language, int(sense["id"])),
                    source_ids=source_ids(str(sense["source_ids"])),
                )
                for sense in senses
            ),
            forms=forms(str(row["forms"])),
            pronunciations=pronunciations(str(row["pronunciations"])),
            etymology=str(row["etymology"]) or None,
            etymology_number=str(row["etymology_number"]) or None,
        )

    def _localized_entry(self, entry: DictionaryEntry) -> DictionaryEntry:
        if self.locale is None:
            return entry
        senses = tuple(
            sorted(
                entry.senses,
                key=lambda sense: _locale_rank(sense.tags, self.locale),
            )
        )
        forms = tuple(sorted(entry.forms, key=lambda form: _locale_rank(form.tags, self.locale)))
        pronunciations = tuple(
            sorted(
                entry.pronunciations,
                key=lambda pronunciation: _locale_rank(pronunciation.tags, self.locale),
            )
        )
        return replace(entry, senses=senses, forms=forms, pronunciations=pronunciations)

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
            entries = tuple(self._localized_entry(self._entry(connection, row)) for row in rows)
            return tuple(
                sorted(
                    entries,
                    key=lambda entry: min(
                        (_locale_rank(sense.tags, self.locale) for sense in entry.senses),
                        default=1,
                    ),
                )
            )

    def senses(self, word: str, *, all_case_variants: bool = False) -> tuple[Sense, ...]:
        return tuple(
            sense
            for entry in self.entries(word, all_case_variants=all_case_variants)
            for sense in entry.senses
        )

    def sense_by_id(self, sense_id: str) -> SenseRecord | None:
        """Return one sense with its entry context by versioned Lexhint ID."""
        self._require("dictionary")
        numeric_id = parse_sense_id(self.language, sense_id)
        if numeric_id is None:
            return None
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT e.* FROM entries AS e JOIN senses AS s ON s.entry_id=e.id WHERE s.id=?",
                (numeric_id,),
            ).fetchone()
            if row is None:
                return None
            entry = self._entry(connection, row)
        sense = next(
            (
                value
                for value in entry.senses
                if value.sense_id == format_sense_id(self.language, numeric_id)
            ),
            None,
        )
        return (
            SenseRecord(entry.word, entry.pos, entry.etymology_number, sense)
            if sense is not None
            else None
        )

    def topics(self, word: str) -> tuple[str, ...]:
        self._require("dictionary")
        normalized = normalize_word(word)
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT DISTINCT t.topic FROM sense_topics AS t "
                "JOIN senses AS s ON s.id=t.sense_id "
                "JOIN entries AS e ON e.id=s.entry_id WHERE e.word=? ORDER BY t.topic",
                (normalized,),
            ).fetchall()
        return tuple(str(row["topic"]) for row in rows)

    def relations(
        self,
        word: str,
        *,
        relation_types: tuple[str, ...] | None = None,
        limit: int = 50,
    ) -> tuple[HeadwordRelation, ...]:
        """Return explicit headword relations without following them implicitly."""
        self._require("dictionary")
        if limit < 0:
            raise ValueError("limit must be >= 0")
        normalized = normalize_word(word)
        query = (
            "SELECT source_word, target_word, relation, tags FROM headword_relations "
            "WHERE source_word=?"
        )
        parameters: list[object] = [normalized]
        if relation_types:
            placeholders = ",".join("?" for _ in relation_types)
            query += f" AND relation IN ({placeholders})"
            parameters.extend(relation_types)
        query += " ORDER BY relation, target_word LIMIT ?"
        parameters.append(limit)
        with closing(self._connect()) as connection:
            rows = connection.execute(query, parameters).fetchall()
        return tuple(
            HeadwordRelation(
                str(row["source_word"]),
                str(row["target_word"]),
                str(row["relation"]),
                self._tuple(str(row["tags"])),
            )
            for row in rows
        )

    def incoming_relations(
        self,
        word: str,
        *,
        relation_types: tuple[str, ...] | None = None,
        limit: int = 50,
    ) -> tuple[HeadwordRelation, ...]:
        """Return headword relations whose target is *word*."""
        self._require("dictionary")
        if limit < 0:
            raise ValueError("limit must be >= 0")
        normalized = normalize_word(word)
        query = (
            "SELECT source_word, target_word, relation, tags FROM headword_relations "
            "WHERE target_word=?"
        )
        parameters: list[object] = [normalized]
        if relation_types:
            placeholders = ",".join("?" for _ in relation_types)
            query += f" AND relation IN ({placeholders})"
            parameters.extend(relation_types)
        query += " ORDER BY relation, source_word LIMIT ?"
        parameters.append(limit)
        with closing(self._connect()) as connection:
            rows = connection.execute(query, parameters).fetchall()
        return tuple(
            HeadwordRelation(
                str(row["source_word"]),
                str(row["target_word"]),
                str(row["relation"]),
                self._tuple(str(row["tags"])),
            )
            for row in rows
        )

    def resolve_headword(
        self,
        word: str,
        *,
        relations: tuple[str, ...] = ("redirect", "alternative", "form_of"),
        limit: int = 20,
    ) -> tuple[str, ...]:
        """Resolve explicit alias relationships to target headwords."""
        return tuple(
            relation.target
            for relation in self.relations(word, relation_types=relations, limit=limit)
        )

    @staticmethod
    def _context_token_distances(
        tokens: list[tuple[str, int, int]], target: tuple[int, int]
    ) -> dict[int, int]:
        start, end = target
        overlapping = {
            i
            for i, (_, token_start, token_end) in enumerate(tokens)
            if start != end and token_start < end and token_end > start
        }
        if overlapping:
            return {
                i: min(abs(i - target_i) for target_i in overlapping)
                for i in range(len(tokens))
                if i not in overlapping
            }

        left_count = sum(token_end <= start for _, _, token_end in tokens)
        distances: dict[int, int] = {}
        for i, (_, token_start, token_end) in enumerate(tokens):
            if token_end <= start:
                distances[i] = left_count - i
            elif token_start >= end:
                distances[i] = i - left_count + 1
            elif start == end:
                distances[i] = 1
        return distances

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
        token_distances = self._context_token_distances(tokens, target)
        if not tokens:
            return ()
        candidate_indices = [i for i, distance in token_distances.items() if distance <= window]
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
            distance = token_distances[index]
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


__all__ = [
    "Lexicon",
    "LexiconCapabilityError",
    "LexiconCoverageError",
    "LexiconIncompatible",
    "LexiconNotInstalled",
]
