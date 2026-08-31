from __future__ import annotations

import json
from pathlib import Path

import pytest

import lexhint.datasets as datasets
from lexhint.builder import build_dictionary
from lexhint.cli import _parser, main

FIXTURE = Path(__file__).parent / "fixtures" / "kaikki-mini.jsonl"


def install_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEXHINT_DATA_DIR", str(tmp_path / "data"))
    source, _ = build_dictionary(
        "en",
        FIXTURE,
        output=tmp_path / "source.sqlite3",
        capabilities="lexical,semantic",
        no_frequency=True,
    )
    target = datasets._artifact_path("en", "runtime", "2026.08.20")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
    artifact = datasets.DatasetArtifact(
        "en",
        "runtime",
        "2026.08.20",
        "data-2026.08.20",
        "2026-08-21T00:00:00Z",
        2,
        "10",
        "runtime",
        "full",
        ("lexical", "semantic"),
        1,
        target.stat().st_size,
        target.name,
        "fixture",
        "",
    )
    datasets._write_sidecar(target.with_name("artifact.json"), artifact, "2026-08-21T00:00:00Z")


def test_dataset_list_json_and_selector(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    install_runtime(tmp_path, monkeypatch)
    assert main(["--json", "dataset", "list"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["installed"][0]["selected"] is True
    assert main(["--json", "word", "compiler", "-l", "en", "--variant", "runtime"]) == 0
    assert json.loads(capsys.readouterr().out)["known"] is True


def test_path_and_variant_conflict_is_controlled(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["word", "compiler", "--path", str(tmp_path / "x"), "--variant", "rich"]) == 1
    assert "cannot be combined" in capsys.readouterr().err


def test_dictionary_variant_is_available_to_dataset_and_query_parsers() -> None:
    parser = _parser()
    download = parser.parse_args(["dataset", "download", "en", "--variant", "dictionary"])
    query = parser.parse_args(["word", "love", "-l", "en", "--variant", "dictionary"])
    assert download.variant == "dictionary"
    assert query.variant == "dictionary"


def test_dataset_available_cli_lists_all_schema10_languages(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    artifacts = tuple(
        datasets.DatasetArtifact(
            language,
            "runtime",
            "2026.08.28",
            f"data-{language}-2026.08.28",
            "2026-09-01T00:00:00Z",
            2,
            datasets.SCHEMA_VERSION,
            "runtime",
            "full",
            ("lexical", "semantic"),
            123,
            456,
            f"lexhint-{language}-runtime-s10-2026.08.28.sqlite3.gz",
            "a" * 64,
            "https://example.test/asset",
        )
        for language in ("cs", "de", "en")
    )
    monkeypatch.setattr("lexhint.cli.available_datasets", lambda **kwargs: artifacts)

    assert main(["dataset", "available"]) == 0
    output = capsys.readouterr().out
    assert "cs runtime s10" in output
    assert "de runtime s10" in output
    assert "en runtime s10" in output

    assert main(["--json", "dataset", "available"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert {item["language"] for item in payload["available"]} == {"cs", "de", "en"}
    assert {item["schema_version"] for item in payload["available"]} == {"10"}
