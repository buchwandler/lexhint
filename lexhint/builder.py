from __future__ import annotations

import gzip
import io
import json
import os
import sqlite3
import tempfile
import urllib.request
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, TextIO
from urllib.parse import urlparse

from .download import cached_dictionary_path
from .lexicon import Lexicon, normalize_word
from .models import DictionaryBuildStats

SCHEMA_VERSION = "1"


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    result: list[str] = []
    for item in value:
        if isinstance(item, str) and item and item not in result:
            result.append(item)
    return tuple(result)


@contextmanager
def _binary_source(source: str | Path, *, timeout: float) -> Iterator[BinaryIO]:
    value = str(source)
    parsed = urlparse(value)
    if parsed.scheme in {"http", "https"}:
        request = urllib.request.Request(
            value,
            headers={"User-Agent": "lexhint/0 (+https://github.com/buchwandler/lexhint)"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            yield response
        return
    with Path(value).expanduser().open("rb") as handle:
        yield handle


@contextmanager
def _text_source(source: str | Path, *, timeout: float = 60.0) -> Iterator[TextIO]:
    value = str(source)
    with _binary_source(source, timeout=timeout) as binary:
        if value.lower().endswith(".gz"):
            with gzip.GzipFile(fileobj=binary, mode="rb") as decompressed:
                with io.TextIOWrapper(decompressed, encoding="utf-8") as text:
                    yield text
        else:
            with io.TextIOWrapper(binary, encoding="utf-8") as text:
                yield text


def iter_wiktextract_entries(source: str | Path, *, timeout: float = 60.0) -> Iterator[dict]:
    """Stream JSONL objects from a local path or HTTP(S) source."""
    with _text_source(source, timeout=timeout) as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at line {line_number}: {exc}") from exc
            if isinstance(value, dict):
                yield value


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA journal_mode=OFF;
        PRAGMA synchronous=OFF;
        PRAGMA temp_store=MEMORY;
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE senses (
            id INTEGER PRIMARY KEY,
            word TEXT NOT NULL,
            display_word TEXT NOT NULL,
            pos TEXT NOT NULL,
            glosses TEXT NOT NULL,
            topics TEXT NOT NULL,
            categories TEXT NOT NULL,
            tags TEXT NOT NULL
        );
        CREATE INDEX senses_word_idx ON senses(word);
        """
    )


def _json_tuple(values: tuple[str, ...]) -> str:
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


def build_dictionary(
    language: str,
    source: str | Path,
    *,
    lexicon: Lexicon | None = None,
    output: str | Path | None = None,
    limit: int = 50_000,
    timeout: float = 60.0,
) -> tuple[Path, DictionaryBuildStats]:
    """Build a compact SQLite dictionary by filtering Wiktextract JSONL to common words."""
    if limit <= 0:
        raise ValueError("limit must be > 0")
    base_language = language.lower().split("-", 1)[0]
    selected_lexicon = lexicon or Lexicon(base_language)
    wanted = set(selected_lexicon.top(limit))
    target = Path(output) if output is not None else cached_dictionary_path(base_language)
    target = target.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(prefix="lexhint-dict-", suffix=".sqlite3", dir=target.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    tmp.unlink(missing_ok=True)

    scanned = 0
    matched = 0
    sense_count = 0
    seen_words: set[str] = set()

    try:
        connection = sqlite3.connect(tmp)
        try:
            _create_schema(connection)
            connection.executemany(
                "INSERT INTO metadata(key, value) VALUES (?, ?)",
                (
                    ("schema_version", SCHEMA_VERSION),
                    ("language", base_language),
                    ("source", str(source)),
                    ("lexicon_limit", str(limit)),
                ),
            )

            for entry in iter_wiktextract_entries(source, timeout=timeout):
                scanned += 1
                if str(entry.get("lang_code") or "").lower() != base_language:
                    continue
                display_word = str(entry.get("word") or "")
                word = normalize_word(display_word)
                if not word or word not in wanted:
                    continue
                matched += 1
                seen_words.add(word)
                pos = str(entry.get("pos") or "")
                entry_topics = _strings(entry.get("topics"))
                entry_categories = _strings(entry.get("categories"))
                entry_tags = _strings(entry.get("tags"))
                senses = entry.get("senses")
                if not isinstance(senses, list):
                    senses = []

                for raw_sense in senses:
                    if not isinstance(raw_sense, Mapping):
                        continue
                    glosses = _strings(raw_sense.get("glosses"))
                    topics = tuple(dict.fromkeys(entry_topics + _strings(raw_sense.get("topics"))))
                    categories = tuple(
                        dict.fromkeys(entry_categories + _strings(raw_sense.get("categories")))
                    )
                    tags = tuple(dict.fromkeys(entry_tags + _strings(raw_sense.get("tags"))))
                    if not (glosses or topics or categories or tags):
                        continue
                    connection.execute(
                        "INSERT INTO senses("
                        "word, display_word, pos, glosses, topics, categories, tags"
                        ") VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            word,
                            display_word,
                            pos,
                            _json_tuple(glosses),
                            _json_tuple(topics),
                            _json_tuple(categories),
                            _json_tuple(tags),
                        ),
                    )
                    sense_count += 1
                if matched % 5000 == 0:
                    connection.commit()

            connection.executemany(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
                (
                    ("scanned_entries", str(scanned)),
                    ("matched_entries", str(matched)),
                    ("words", str(len(seen_words))),
                    ("senses", str(sense_count)),
                ),
            )
            connection.commit()
            connection.execute("ANALYZE")
            connection.commit()
        finally:
            connection.close()
        tmp.replace(target)
    finally:
        tmp.unlink(missing_ok=True)

    return target, DictionaryBuildStats(scanned, matched, len(seen_words), sense_count)
