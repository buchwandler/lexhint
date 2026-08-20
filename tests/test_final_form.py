from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from lexhint import (
    Lexicon,
    LexiconCapabilityError,
    LexiconCoverageError,
    LexiconIncompatible,
    SemanticDomain,
)
from lexhint.builder import build_dictionary
from lexhint.cli import main
from lexhint.models import LexicalSegment
from lexhint.schema import normalize_capabilities

FIXTURE = Path(__file__).parent / "fixtures" / "kaikki-mini.jsonl"


def build(
    tmp_path: Path, *, capabilities: str | None = None, frequency: Path | None = None
) -> Lexicon:
    path, _ = build_dictionary(
        "en",
        FIXTURE,
        output=tmp_path / "en.sqlite3",
        capabilities=capabilities,
        frequency_source=frequency,
        no_frequency=frequency is None,
    )
    return Lexicon.from_path(path)


def test_runtime_word_segmentation_and_rich_lookup_are_local(tmp_path: Path) -> None:
    source = tmp_path / "words.jsonl"
    source.write_text(
        "".join(
            json.dumps(
                {"word": word, "lang_code": "en", "pos": "noun", "senses": [{"glosses": [word]}]}
            )
            + "\n"
            for word in ("chat", "GPT", "compiler", "word")
        ),
        encoding="utf-8",
    )
    path, _ = build_dictionary("en", source, output=tmp_path / "en.sqlite3", no_frequency=True)
    lexicon = Lexicon.from_path(path)
    assert lexicon.word("compiler").known
    assert lexicon.segment("compilerword") == (
        LexicalSegment("compiler", True),
        LexicalSegment("word", True),
    )
    assert lexicon.segment("chatgpt") == (
        LexicalSegment("chat", True),
        LexicalSegment("gpt", False),
    )
    assert lexicon.entries("compiler")[0].word == "compiler"


def test_partial_coverage_is_rejected(tmp_path: Path) -> None:
    lexicon = build(tmp_path)
    with sqlite3.connect(lexicon.path) as connection:
        connection.execute("UPDATE metadata SET value='partial' WHERE key='coverage'")
    with pytest.raises(LexiconCoverageError):
        Lexicon.from_path(lexicon.path).segment("compilerword")


def test_capabilities_are_conditional_and_canonical(tmp_path: Path) -> None:
    selection = normalize_capabilities("semantic,lexical")
    assert selection.capabilities == ("lexical", "semantic")
    path, _ = build_dictionary(
        "en",
        FIXTURE,
        output=tmp_path / "lexical.sqlite3",
        capabilities="lexical",
        no_frequency=True,
    )
    lexicon = Lexicon.from_path(path)
    assert lexicon.metadata["capabilities"] == "lexical"
    with pytest.raises(LexiconCapabilityError):
        lexicon.entries("compiler")
    with pytest.raises(LexiconCapabilityError):
        lexicon.context_domains("The compiler is 8.3.2.", target=(16, 21))
    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "lexeme_domains" not in tables
    assert "entries" not in tables


def test_semantic_context_is_ranked_explainable_and_excludes_target(tmp_path: Path) -> None:
    lexicon = build(tmp_path)
    text = "The compiler is 8.3.2."
    target = (text.index("8.3.2"), len(text))
    evidence = lexicon.supports_domain(text, target=target, domain=SemanticDomain.COMPUTING)
    assert evidence is not None
    assert evidence.cues[0].text == "compiler"
    assert lexicon.supports_domain("scale", target=(0, 5), domain="music") is None

    music = "The scale is Am."
    music_target = (music.index("Am"), music.index("Am") + 2)
    music_evidence = lexicon.supports_domain(music, target=music_target, domain="music")
    assert music_evidence is not None
    assert music_evidence.cues[0].text == "scale"
    assert lexicon.context_domains(text, target=target, window=0) == ()


def test_frequency_enriches_existing_lexemes_only(tmp_path: Path) -> None:
    frequency = tmp_path / "en_full.txt"
    frequency.write_text("compiler 100\ncorpusonly 20\n", encoding="utf-8")
    lexicon = build(tmp_path, frequency=frequency)
    info = lexicon.word("compiler")
    assert (info.frequency_rank, info.frequency_count) == (1, 100)
    assert not lexicon.contains("corpusonly")
    assert lexicon.metadata["frequency_source"] == "custom"
    assert (
        lexicon.metadata["frequency_source_sha256"]
        == hashlib.sha256(frequency.read_bytes()).hexdigest()
    )


def test_schema_and_language_errors_are_controlled(tmp_path: Path) -> None:
    path = tmp_path / "bad.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        connection.execute("INSERT INTO metadata VALUES ('schema_version', '1')")
        connection.execute("INSERT INTO metadata VALUES ('language', 'en')")
        connection.commit()
    with pytest.raises(LexiconIncompatible, match="schema 1"):
        Lexicon.from_path(path)


def test_cli_context_and_capability_build(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path, _ = build_dictionary("en", FIXTURE, output=tmp_path / "en.sqlite3", no_frequency=True)
    assert (
        main(
            [
                "--json",
                "context",
                "--path",
                str(path),
                "The compiler is 8.3.2.",
                "--target",
                "15:20",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["domains"][0]["domain"] == "computing"
    assert (
        main(
            [
                "--json",
                "dictionary",
                "build",
                "en",
                "--source",
                str(FIXTURE),
                "--output",
                str(tmp_path / "lexical.sqlite3"),
                "--capabilities",
                "lexical",
                "--no-frequency",
            ]
        )
        == 0
    )
    built = json.loads(capsys.readouterr().out)
    assert built["capabilities"] == ["lexical"]


def test_runtime_is_no_network_and_no_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, _ = build_dictionary("en", FIXTURE, output=tmp_path / "en.sqlite3", no_frequency=True)
    before = hashlib.sha256(path.read_bytes()).digest()
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *args, **kwargs: pytest.fail("runtime used network")
    )
    lexicon = Lexicon.from_path(path)
    lexicon.word("compiler")
    lexicon.contains("scale")
    lexicon.segment("compilerword")
    lexicon.context_domains("The compiler is 8.3.2.", target=(16, 21))
    lexicon.supports_domain("The scale is Am.", target=(14, 16), domain="music")
    lexicon.entries("compiler")
    assert hashlib.sha256(path.read_bytes()).digest() == before
