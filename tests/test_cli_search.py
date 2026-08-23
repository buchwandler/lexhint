from __future__ import annotations

import json
from pathlib import Path

import pytest

from lexhint.builder import build_dictionary
from lexhint.cli import main

FIXTURE = Path(__file__).parent / "fixtures" / "kaikki-mini.jsonl"


@pytest.fixture
def artifact(tmp_path: Path) -> Path:
    path, _ = build_dictionary(
        "en", FIXTURE, output=tmp_path / "rich.sqlite3", profile="rich", no_frequency=True
    )
    return path


def test_search_cli_human_and_json(artifact: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["suggest", "complier", "--path", str(artifact)]) == 0
    assert capsys.readouterr().out.strip() == "compiler"

    assert main(["headwords", "comp*", "--path", str(artifact)]) == 0
    assert capsys.readouterr().out.strip() == "compiler"

    assert (
        main(["--json", "dictionary", "search", "computer program", "--path", str(artifact)]) == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["query"] == "computer program"
    assert payload["hits"][0]["word"] == "compiler"
