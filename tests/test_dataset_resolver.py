from __future__ import annotations

from pathlib import Path

import pytest

import lexhint.datasets as datasets
from lexhint import Lexicon
from lexhint.builder import build_dictionary

FIXTURE = Path(__file__).parent / "fixtures" / "kaikki-mini.jsonl"


def install_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    variant: str,
    version: str = "2026.08.20",
) -> Path:
    monkeypatch.setenv("LEXHINT_DATA_DIR", str(tmp_path / "data"))
    capabilities = {
        "lexical": ("lexical", "custom"),
        "runtime": ("lexical,semantic", "runtime"),
        "rich": ("lexical,semantic,dictionary,search", "rich"),
    }[variant]
    source, _ = build_dictionary(
        "en",
        FIXTURE,
        output=tmp_path / f"{variant}-{version}.sqlite3",
        capabilities=capabilities[0],
        no_frequency=True,
    )
    target = datasets._artifact_path("en", variant, version)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
    artifact = datasets.DatasetArtifact(
        "en",
        variant,
        version,
        f"data-{version}",
        "2026-08-21T00:00:00Z",
        2,
        "8",
        capabilities[1],
        "full",
        tuple(capabilities[0].split(",")),
        1,
        target.stat().st_size,
        target.name,
        "fixture",
        "",
    )
    datasets._write_sidecar(target.with_name("artifact.json"), artifact, version)
    return target


def test_highest_installed_capability_and_explicit_selection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lexical = install_fixture(tmp_path, monkeypatch, "lexical")
    runtime = install_fixture(tmp_path, monkeypatch, "runtime")
    assert datasets.resolve_installed_dataset("en").path == runtime
    assert Lexicon("en").path == runtime
    assert datasets.resolve_installed_dataset("en", variant="lexical").path == lexical


def test_newest_version_and_removal_are_side_by_side(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = install_fixture(tmp_path, monkeypatch, "runtime", "2026.08.20")
    new = install_fixture(tmp_path, monkeypatch, "runtime", "2026.09.01")
    assert datasets.resolve_installed_dataset("en", variant="runtime").path == new
    assert datasets.remove_dataset("en", variant="runtime", version="2026.09.01") == (new,)
    assert old.exists()


def test_runtime_resolution_never_downloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LEXHINT_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(datasets, "request", lambda *args, **kwargs: pytest.fail("network used"))
    monkeypatch.setattr(
        "lexhint.lexicon.cached_dictionary_path", lambda language: tmp_path / "missing.sqlite3"
    )
    with pytest.raises(FileNotFoundError):
        Lexicon("en")
