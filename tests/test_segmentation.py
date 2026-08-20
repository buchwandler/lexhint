import json
from pathlib import Path

import pytest

from lexhint import Dictionary, DictionaryCoverageError
from lexhint.builder import build_dictionary
from lexhint.models import LexicalSegment


def _build(tmp_path: Path, *, coverage: str = "full") -> Dictionary:
    source = tmp_path / "dictionary.jsonl"
    entries = [
        "compiler",
        "word",
        "com",
        "pil",
        "er",
        "chat",
        "GPT",
    ]
    with source.open("w", encoding="utf-8") as handle:
        for word in entries:
            handle.write(
                json.dumps(
                    {
                        "word": word,
                        "lang_code": "en",
                        "pos": "noun",
                        "senses": [{"glosses": [word]}],
                    }
                )
                + "\n"
            )
    path, _ = build_dictionary("en", source, output=tmp_path / "en.sqlite3")
    if coverage == "partial":
        import sqlite3

        with sqlite3.connect(path) as connection:
            connection.execute("UPDATE metadata SET value = 'partial' WHERE key = 'coverage'")
            connection.commit()
    return Dictionary.from_path(path)


def test_compilerword_prefers_dictionary_headword(tmp_path: Path) -> None:
    dictionary = _build(tmp_path)
    assert dictionary.segment("compilerword") == (
        LexicalSegment("compiler", True),
        LexicalSegment("word", True),
    )


def test_dictionary_only_word_is_known_without_frequency(tmp_path: Path) -> None:
    dictionary = _build(tmp_path)
    info = dictionary.word_info("compiler")
    assert info.known
    assert info.frequency_rank is None
    assert info.frequency_count is None


def test_partial_coverage_rejects_segmentation(tmp_path: Path) -> None:
    dictionary = _build(tmp_path, coverage="partial")
    with pytest.raises(DictionaryCoverageError, match="full lexical coverage"):
        dictionary.segment("compilerword")


def test_lowercase_segmentation_ignores_uppercase_only_entry(tmp_path: Path) -> None:
    dictionary = _build(tmp_path)
    segments = dictionary.segment("chatgpt")
    assert segments[0] == LexicalSegment("chat", True)
    assert all(segment.text != "gpt" or not segment.known for segment in segments)
