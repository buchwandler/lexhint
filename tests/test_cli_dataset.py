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
        "8",
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
