from __future__ import annotations

import gzip
import math
import unicodedata
from collections.abc import Iterable
from functools import lru_cache
from importlib.resources import files
from pathlib import Path

from .download import cached_wordlist_path, fetch_wordlist
from .models import Segment

_MAX_TWO_LETTER_RANK = 2_000


class LexiconNotInstalled(FileNotFoundError):
    """Raised when a requested language word list is not locally available."""


def normalize_word(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


@lru_cache(maxsize=16)
def _load_path(path: str) -> tuple[str, ...]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return tuple(line.strip() for line in handle if line.strip())


class Lexicon:
    """Frequency-ranked common-word lexicon.

    Rank is one-based and follows source list order. Word lists are loaded lazily.
    """

    def __init__(
        self,
        language: str,
        *,
        auto_fetch: bool = False,
        path: str | Path | None = None,
        words: Iterable[str] | None = None,
    ) -> None:
        self.language = language.lower().split("-", 1)[0]
        self._explicit_path = Path(path) if path is not None else None
        self._inline_words = tuple(words) if words is not None else None
        self._auto_fetch = auto_fetch
        self._words: tuple[str, ...] | None = None
        self._ranks: dict[str, int] | None = None

    @classmethod
    def from_words(cls, words: Iterable[str], *, language: str = "und") -> Lexicon:
        return cls(language, words=words)

    def _resolve_path(self) -> Path:
        if self._explicit_path is not None:
            return self._explicit_path

        vendored = (
            files("lexhint").joinpath("data").joinpath("words").joinpath(f"{self.language}.txt.gz")
        )
        try:
            if vendored.is_file():
                return Path(str(vendored))
        except TypeError:
            pass

        cached = cached_wordlist_path(self.language)
        if cached.exists():
            return cached
        if self._auto_fetch:
            return fetch_wordlist(self.language)
        raise LexiconNotInstalled(
            f"no word list installed for {self.language!r}; "
            f"run 'lexhint setup {self.language}' or pass auto_fetch=True"
        )

    def _ensure_loaded(self) -> None:
        if self._words is not None:
            return
        if self._inline_words is not None:
            normalized: list[str] = []
            seen: set[str] = set()
            for value in self._inline_words:
                word = normalize_word(value)
                if word and word not in seen:
                    seen.add(word)
                    normalized.append(word)
            self._words = tuple(normalized)
        else:
            self._words = _load_path(str(self._resolve_path().resolve()))
        self._ranks = {word: rank for rank, word in enumerate(self._words, start=1)}

    def __len__(self) -> int:
        self._ensure_loaded()
        assert self._words is not None
        return len(self._words)

    def contains(self, word: str) -> bool:
        self._ensure_loaded()
        assert self._ranks is not None
        return normalize_word(word) in self._ranks

    def __contains__(self, word: object) -> bool:
        return isinstance(word, str) and self.contains(word)

    def rank(self, word: str) -> int | None:
        self._ensure_loaded()
        assert self._ranks is not None
        return self._ranks.get(normalize_word(word))

    def top(self, n: int) -> tuple[str, ...]:
        if n < 0:
            raise ValueError("n must be >= 0")
        self._ensure_loaded()
        assert self._words is not None
        return self._words[:n]

    def segment(self, text: str, *, max_word_length: int = 32) -> tuple[Segment, ...]:
        """Split a compact identifier into common words and unknown runs.

        The dynamic program rewards longer common words, mildly rewards high rank,
        and penalizes unknown characters. One-letter lexicon matches are ignored so
        residual initialisms remain grouped for a speech layer to spell later.
        """
        value = normalize_word(text)
        if not value:
            return ()
        self._ensure_loaded()
        assert self._ranks is not None

        n = len(value)
        best = [-math.inf] * (n + 1)
        previous: list[tuple[int, bool, int | None] | None] = [None] * (n + 1)
        best[0] = 0.0

        for end in range(1, n + 1):
            unknown_score = best[end - 1] - 5.0
            if unknown_score > best[end]:
                best[end] = unknown_score
                previous[end] = (end - 1, False, None)

            start_min = max(0, end - max_word_length)
            for start in range(start_min, end - 1):
                candidate = value[start:end]
                rank = self._ranks.get(candidate)
                if rank is None:
                    continue
                length = end - start
                # Two-letter matches are useful for very common function words ("at",
                # "in", "to"), but obscure abbreviations should not consume part of an
                # otherwise unknown initialism. Without this guard, a frequency-list entry
                # such as "gp" can turn "chatgpt" into "chat" + "gp" + "t".
                if length == 2 and rank > _MAX_TWO_LETTER_RANK:
                    continue
                score = best[start] + (length * 6.0) - math.log10(rank + 9)
                if score > best[end]:
                    best[end] = score
                    previous[end] = (start, True, rank)

        raw: list[Segment] = []
        cursor = n
        while cursor > 0:
            step = previous[cursor] or (cursor - 1, False, None)
            start, known, rank = step
            raw.append(Segment(value[start:cursor], known=known, rank=rank))
            cursor = start
        raw.reverse()

        merged: list[Segment] = []
        for item in raw:
            if not item.known and merged and not merged[-1].known:
                merged[-1] = Segment(merged[-1].text + item.text, known=False)
            else:
                merged.append(item)
        return tuple(merged)
