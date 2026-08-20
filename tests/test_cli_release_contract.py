from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from lexhint.cli import main


def test_missing_artifact_human_error_is_controlled(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing.sqlite3"

    assert main(["word", "compiler", "--path", str(missing)]) == 1

    captured = capsys.readouterr()
    assert "no local lexicon artifact" in captured.err
    assert "dictionary build" in captured.err
    assert not missing.exists()


def test_missing_artifact_json_error_is_controlled(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "missing.sqlite3"

    assert main(["--json", "word", "compiler", "--path", str(missing)]) == 1

    captured = capsys.readouterr()
    assert '"error"' in captured.err
    assert '"hint"' in captured.err
    assert not missing.exists()


def test_python_module_entrypoint_help() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "lexhint", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "Local lexical evidence" in result.stdout
    assert result.stderr == ""
