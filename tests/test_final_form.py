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
    LexiconNotInstalled,
    SemanticDomain,
)
from lexhint.builder import build_dictionary
from lexhint.cli import main
from lexhint.models import LexicalSegment
from lexhint.schema import normalize_capabilities
from lexhint.status import read_artifact_status

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


def test_status_reports_current_capability_aware_counts(tmp_path: Path) -> None:
    path, _ = build_dictionary(
        "en",
        FIXTURE,
        output=tmp_path / "runtime.sqlite3",
        capabilities="lexical",
        no_frequency=True,
    )
    result = read_artifact_status("en", path=path)
    assert result.counts == {
        "lexemes": 4,
        "semantic_rows": None,
        "entries": None,
        "senses": None,
        "frequency_lexemes": 0,
    }
    assert result.profile == "custom"


def test_cli_build_progress_is_stderr_and_json_is_single_stdout_document(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "en.sqlite3"
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
                str(output),
                "--no-frequency",
            ]
        )
        == 0
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["path"] == str(output)
    assert captured.out.count("\n") == 1
    assert "Building Lexhint database" in captured.err
    assert "scanned" in captured.err


def test_dictionary_status_cli_supports_default_and_explicit_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("LEXHINT_CACHE_DIR", str(tmp_path / "cache"))
    path, _ = build_dictionary("en", FIXTURE, no_frequency=True)
    assert main(["--json", "dictionary", "status"]) == 0
    default_status = json.loads(capsys.readouterr().out)
    assert default_status["path"] == str(path)
    assert default_status["counts"]["lexemes"] == 4
    assert main(["--json", "dictionary", "status", "--path", str(path)]) == 0
    explicit_status = json.loads(capsys.readouterr().out)
    assert explicit_status["path"] == str(path)


def test_build_option_conflicts_and_capability_validation(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no-frequency"):
        build_dictionary(
            "en",
            FIXTURE,
            output=tmp_path / "one.sqlite3",
            no_frequency=True,
            frequency_source=FIXTURE,
        )
    with pytest.raises(ValueError, match="requires"):
        build_dictionary(
            "en",
            FIXTURE,
            output=tmp_path / "two.sqlite3",
            capabilities="semantic",
            no_frequency=True,
        )
    with pytest.raises(ValueError, match="unknown capability"):
        build_dictionary(
            "en",
            FIXTURE,
            output=tmp_path / "three.sqlite3",
            capabilities="lexical,unknown",
            no_frequency=True,
        )


def test_missing_artifact_is_not_created(tmp_path: Path) -> None:
    missing = tmp_path / "missing.sqlite3"
    with pytest.raises(LexiconNotInstalled):
        Lexicon.from_path(missing)
    assert not missing.exists()


def test_offline_rejects_remote_dictionary_before_urlopen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *args, **kwargs: pytest.fail("network was called")
    )
    with pytest.raises(OSError, match="offline"):
        build_dictionary(
            "en",
            "https://example.invalid/source.jsonl",
            output=tmp_path / "remote.sqlite3",
            no_frequency=True,
            offline=True,
        )


def test_rich_status_reports_database_counts(tmp_path: Path) -> None:
    path, _ = build_dictionary("en", FIXTURE, output=tmp_path / "rich.sqlite3", no_frequency=True)
    status = read_artifact_status("en", path=path)
    assert status.counts["entries"] == 5
    assert status.counts["senses"] == 9
    assert status.counts["semantic_rows"] == 3
    assert status.counts["frequency_lexemes"] == 0
