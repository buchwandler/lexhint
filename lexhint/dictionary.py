from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from importlib.resources import files
from pathlib import Path
from collections.abc import Iterable

from .download import cached_dictionary_path
from .models import ContextSupport, Sense, TopicScore

_WORD_RE = re.compile(r"[^\W\d_]+(?:[-'][^\W\d_]+)*", re.UNICODE)


class DictionaryNotInstalled(FileNotFoundError):
    """Raised when a compact dictionary index is not locally available."""


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def _loads_tuple(value: str) -> tuple[str, ...]:
    data = json.loads(value)
    return tuple(str(item) for item in data)


class Dictionary:
    """Read-only compact dictionary index generated from Wiktextract/Kaikki JSONL."""

    def __init__(self, language: str, *, path: str | Path | None = None) -> None:
        self.language = language.lower().split("-", 1)[0]
        self.path = Path(path) if path is not None else self._resolve_path()
        if not self.path.is_file():
            raise DictionaryNotInstalled(
                f"no dictionary index installed for {self.language!r}; "
                "run 'lexhint dictionary build ...'"
            )

    @classmethod
    def from_path(cls, path: str | Path, *, language: str = "und") -> Dictionary:
        return cls(language, path=path)

    def _resolve_path(self) -> Path:
        vendored = files("lexhint").joinpath("data", "dictionaries", f"{self.language}.sqlite3")
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

    def senses(self, word: str) -> tuple[Sense, ...]:
        normalized = _normalize(word)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT display_word, pos, glosses, topics, categories, tags "
                "FROM senses WHERE word = ? ORDER BY id",
                (normalized,),
            ).fetchall()
        return tuple(
            Sense(
                word=str(row["display_word"]),
                pos=str(row["pos"]),
                glosses=_loads_tuple(str(row["glosses"])),
                topics=_loads_tuple(str(row["topics"])),
                categories=_loads_tuple(str(row["categories"])),
                tags=_loads_tuple(str(row["tags"])),
            )
            for row in rows
        )

    def contains(self, word: str) -> bool:
        normalized = _normalize(word)
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM senses WHERE word = ? LIMIT 1", (normalized,)
            ).fetchone()
        return row is not None

    def topics(self, word: str) -> tuple[str, ...]:
        values: set[str] = set()
        for sense in self.senses(word):
            values.update(sense.topics)
        return tuple(sorted(values))

    def _topics_for_words(self, words: Iterable[str]) -> dict[str, set[str]]:
        normalized = tuple(dict.fromkeys(_normalize(word) for word in words if word))
        if not normalized:
            return {}
        result: dict[str, set[str]] = {word: set() for word in normalized}
        with self._connect() as connection:
            for offset in range(0, len(normalized), 500):
                chunk = normalized[offset : offset + 500]
                placeholders = ",".join("?" for _ in chunk)
                rows = connection.execute(
                    f"SELECT word, topics FROM senses WHERE word IN ({placeholders})",  # noqa: S608
                    chunk,
                ).fetchall()
                for row in rows:
                    result[str(row["word"])].update(_loads_tuple(str(row["topics"])))
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
    ) -> tuple[TopicScore, ...]:
        """Aggregate nearby dictionary topics around a source span.

        The target token itself is excluded so a candidate cannot validate itself.
        This is diagnostic context evidence, not general-purpose word-sense disambiguation.
        """
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
        topics_by_word = self._topics_for_words(token for token, _, _ in tokens)

        scores: dict[str, float] = {}
        cues: dict[str, list[str]] = {}
        for index, (token, _, _) in enumerate(tokens):
            if index in target_indices:
                continue
            distance = min(abs(index - target_index) for target_index in target_indices)
            if distance > window:
                continue
            normalized = _normalize(token)
            for topic in topics_by_word.get(normalized, ()):
                key = _normalize(topic)
                scores[key] = scores.get(key, 0.0) + decay**distance
                cues.setdefault(key, []).append(token)

        ranked = [
            TopicScore(topic, score, tuple(dict.fromkeys(cues[topic])))
            for topic, score in scores.items()
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
    ) -> ContextSupport | None:
        """Return nearby dictionary evidence for a requested semantic topic."""
        wanted = _normalize(topic)
        for score in self.topic_scores(text, target=target, window=window, decay=decay, limit=None):
            if _normalize(score.topic) == wanted and score.score >= threshold:
                return ContextSupport(score.topic, score.score, score.cues)
        return None
