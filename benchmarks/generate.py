"""Deterministic pseudo-language dictionary generation."""

from __future__ import annotations

import json
import random
import string
from collections.abc import Iterator

from .model import SyntheticEntry, SyntheticLexeme, SyntheticProfile, SyntheticSense

ONSETS = (
    "b",
    "br",
    "c",
    "ch",
    "cl",
    "d",
    "f",
    "fl",
    "g",
    "gr",
    "h",
    "j",
    "k",
    "l",
    "m",
    "n",
    "p",
    "pr",
    "r",
    "s",
    "sh",
    "st",
    "t",
    "tr",
    "v",
    "w",
    "y",
    "z",
)
VOWELS = ("a", "e", "i", "o", "u", "ea", "ee", "ai", "ou", "oi")
CODAS = ("", "n", "r", "s", "t", "d", "l", "m", "nd", "st", "th")
POS = ("noun", "verb", "adjective", "adverb", "preposition")
DOMAINS = (
    "computing",
    "communication",
    "finance",
    "law",
    "sports",
    "music",
    "biology",
    "medicine",
    "chemistry",
    "geography",
)
SEARCH_VOCABULARY = (
    "object",
    "person",
    "system",
    "action",
    "process",
    "place",
    "method",
    "language",
    "computer",
    "device",
    "move",
    "make",
    "use",
    "small",
    "large",
    "formal",
    "informal",
    "historical",
    "modern",
    "common",
    "rare",
    "structure",
    "change",
    "create",
    "measure",
    "value",
    "order",
    "natural",
    "example",
    "meaning",
    "sound",
    "word",
    "group",
    "part",
    "property",
    "related",
    "technical",
    "general",
    "local",
    "pattern",
)
PREFIX_FAMILIES = (
    (
        "comp",
        ("compile", "compiler", "compilation", "compilable", "computal", "computer", "computing"),
    ),
    ("trans", ("transfer", "transform", "transformed", "translation", "transistor", "transitive")),
    ("graph", ("graph", "graphic", "graphed", "graphical", "graphing", "grapher")),
    ("inter", ("interact", "interaction", "interactive", "interface", "internal", "interval")),
)


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _count(mean: float, rng: random.Random, minimum: int = 0) -> int:
    whole = int(mean)
    return max(minimum, whole + int(rng.random() < (mean - whole)))


def _repeat_sentence(vocabulary: tuple[str, ...], length: int, start: int) -> str:
    if length <= 0:
        return ""
    words: list[str] = []
    index = start % len(vocabulary)
    while len(" ".join(words)) < length:
        words.append(vocabulary[index % len(vocabulary)])
        index += 1
    return " ".join(words)[:length].rstrip()


class SyntheticGenerator:
    """Generate stable rows without retaining the complete dictionary."""

    def __init__(self, profile: SyntheticProfile):
        self.profile = profile
        self._family_words = tuple(word for _, words in PREFIX_FAMILIES for word in words)

    def _word(self, index: int) -> str:
        if index < len(self._family_words):
            return self._family_words[index]
        rng = random.Random(self.profile.seed * 1_000_003 + index * 9_176 + 31)
        syllables = 2 + rng.randrange(4)
        word = "".join(
            rng.choice(ONSETS) + rng.choice(VOWELS) + rng.choice(CODAS) for _ in range(syllables)
        )
        # A pronounceable base-26 suffix makes the key unique without a global seen set.
        number = index - len(self._family_words)
        suffix = ""
        while number or not suffix:
            suffix = string.ascii_lowercase[number % 26] + suffix
            number //= 26
        return f"{word}{suffix}"

    def _entry_count(self, index: int) -> int:
        return _count(self.profile.entries_per_lexeme_mean, self._rng(index, 11), minimum=1)

    def _rng(self, index: int, salt: int) -> random.Random:
        return random.Random(self.profile.seed * 1_000_003 + index * 9_176 + salt)

    def _lexeme(self, index: int) -> SyntheticLexeme:
        word = self._word(index)
        rng = self._rng(index, 13)
        corpus_count = (
            int(10 + rng.random() * 9_990)
            if rng.random() < self.profile.frequency_coverage
            else None
        )
        corpus_rank = index + 1 if corpus_count is not None else None
        return SyntheticLexeme(
            word, word, self._entry_count(index), True, False, False, corpus_count, corpus_rank
        )

    def iter_lexemes(self) -> Iterator[SyntheticLexeme]:
        for index in range(self.profile.lexemes):
            yield self._lexeme(index)

    def _text(self, length: int, start: int) -> str:
        return _repeat_sentence(SEARCH_VOCABULARY, length, start)

    def _entry(self, lexeme_index: int, entry_index: int, entry_id: int) -> SyntheticEntry:
        profile = self.profile
        rng = self._rng(lexeme_index * 100 + entry_index, 17)
        word = self._word(lexeme_index)
        etymology = ""
        if rng.random() < profile.etymology_probability:
            etymology = self._text(profile.etymology_length_mean, lexeme_index + entry_index)
        forms = [
            {"form": f"{word}{suffix}", "tags": ["plural"]}
            for suffix in ("s", "ed", "ing")[: _count(profile.forms_per_entry_mean, rng)]
        ]
        pronunciations = [
            {"ipa": f"/{word[: max(1, min(6, len(word)))]}/", "tags": ["general"]}
            for _ in range(_count(profile.pronunciations_per_entry_mean, rng))
        ]
        return SyntheticEntry(
            entry_id,
            word,
            word,
            POS[entry_index % len(POS)],
            entry_index,
            etymology,
            _json(forms),
            _json(pronunciations),
        )

    def iter_entries(self) -> Iterator[SyntheticEntry]:
        entry_id = 1
        for lexeme_index in range(self.profile.lexemes):
            for entry_index in range(self._entry_count(lexeme_index)):
                yield self._entry(lexeme_index, entry_index, entry_id)
                entry_id += 1

    def _sense(
        self, lexeme_index: int, entry: SyntheticEntry, sense_index: int, sense_id: int
    ) -> SyntheticSense:
        profile = self.profile
        rng = self._rng(sense_id, 23)
        vocabulary = SEARCH_VOCABULARY

        def words(mean: float, offset: int) -> tuple[str, ...]:
            count = _count(mean, rng)
            return tuple(vocabulary[(offset + i * 3) % len(vocabulary)] for i in range(count))

        glosses = tuple(
            self._text(profile.gloss_length_mean, lexeme_index + sense_index + i * 7)
            for i in range(_count(profile.glosses_per_sense_mean, rng, minimum=1))
        )
        topics = words(profile.topics_per_sense_mean, lexeme_index)
        tags = words(profile.tags_per_sense_mean, sense_id)
        examples = tuple(
            {
                "text": self._text(profile.example_length_mean, sense_id + i),
                "translation": self._text(24, sense_id + i + 3)
                if rng.random() < profile.example_translation_probability
                else None,
            }
            for i in range(_count(profile.examples_per_sense_mean, rng))
        )
        synonyms = tuple(
            self._word((lexeme_index + i + 1) % profile.lexemes)
            for i in range(_count(profile.synonyms_per_sense_mean, rng))
        )
        antonyms = tuple(
            self._word((lexeme_index + i + 17) % profile.lexemes)
            for i in range(_count(profile.antonyms_per_sense_mean, rng))
        )
        fields = (
            ("glosses", glosses),
            ("topics", topics),
            ("tags", tags),
            ("examples", tuple(item["text"] for item in examples)),
            ("synonyms", synonyms),
            ("antonyms", antonyms),
        )
        return SyntheticSense(
            sense_id,
            entry.entry_id,
            entry.word,
            sense_index,
            _json(glosses),
            _json(topics),
            _json(tags),
            _json(examples),
            _json(synonyms),
            _json(antonyms),
            fields,
        )

    def iter_senses(self) -> Iterator[SyntheticSense]:
        sense_id = 1
        entry_id = 1
        for lexeme_index in range(self.profile.lexemes):
            for entry_index in range(self._entry_count(lexeme_index)):
                entry = self._entry(lexeme_index, entry_index, entry_id)
                sense_count = _count(
                    self.profile.senses_per_entry_mean, self._rng(entry_id, 19), minimum=1
                )
                for sense_index in range(sense_count):
                    yield self._sense(lexeme_index, entry, sense_index, sense_id)
                    sense_id += 1
                entry_id += 1

    def counts(self) -> dict[str, int]:
        lexemes = self.profile.lexemes
        entries = senses = semantic = ngrams = search_terms = 0
        entry_id = 1
        for lexeme_index in range(lexemes):
            entry_count = self._entry_count(lexeme_index)
            entries += entry_count
            if self._rng(lexeme_index, 29).random() < self.profile.semantic_coverage:
                semantic += _count(
                    self.profile.domains_per_semantic_lexeme_mean,
                    self._rng(lexeme_index, 31),
                    minimum=1,
                )
            ngrams += len(self._ngrams(self._word(lexeme_index)))
            for _ in range(entry_count):
                senses += _count(
                    self.profile.senses_per_entry_mean, self._rng(entry_id, 19), minimum=1
                )
                entry_id += 1
        # Search rows are derived from the same sense stream, avoiding an in-memory index.
        for sense in self.iter_senses():
            search_terms += sum(
                len({token for item in values for token in item.split()})
                for _, values in sense.search_fields
            )
        return {
            "lexemes": lexemes,
            "entries": entries,
            "senses": senses,
            "semantic_rows": semantic,
            "lexeme_ngrams": ngrams,
            "sense_search_terms": search_terms,
        }

    @staticmethod
    def _ngrams(word: str) -> tuple[str, ...]:
        padded = f"^{word}$"
        result: list[str] = []
        for size in (2, 3) if len(word) >= 3 else (2,):
            result.extend(padded[i : i + size] for i in range(len(padded) - size + 1))
        return tuple(dict.fromkeys(result))

    def query_corpus(self) -> dict[str, list[str]]:
        words = [self._word(i) for i in range(self.profile.lexemes)]
        if not words:
            return {}
        common = words[0]
        rare = words[-1]
        return {
            "exact_hits": [common, words[len(words) // 2], rare],
            "exact_misses": ["zzzzmissing", "q" * 18],
            "prefix_narrow": [common[: max(2, len(common) - 2)]],
            "prefix_medium": [common[:2]],
            "prefix_broad": [common[:1]],
            "prefix_no_match": ["zzzz"],
            "dictionary_words_simple": [words[0]],
            "dictionary_words_dense": [words[min(len(words) - 1, max(0, len(words) // 3))]],
            "suggest_distance_1": [common[:-1] if len(common) > 2 else common + "a"],
            "suggest_distance_2": [common[:-1] + "x" if len(common) > 2 else common + "ab"],
            "definition_rare": ["historical"],
            "definition_common": ["object"],
            "definition_multi_all": ["object", "system"],
            "definition_multi_any": ["object", "rare"],
        }
