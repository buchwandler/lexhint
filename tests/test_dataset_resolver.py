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
        "dictionary": ("lexical,semantic,dictionary", "custom"),
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
        "9",
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


def test_capability_chain_resolves_each_maximal_variant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cases = (
        ("lexical", ("lexical",), "lexical"),
        ("runtime", ("lexical", "runtime"), "runtime"),
        ("dictionary", ("runtime", "dictionary"), "dictionary"),
        ("rich", ("dictionary", "rich"), "rich"),
        ("all", ("lexical", "runtime", "dictionary", "rich"), "rich"),
    )
    for name, variants, expected in cases:
        case_dir = tmp_path / name
        case_dir.mkdir()
        installed = {
            variant: install_fixture(case_dir, monkeypatch, variant) for variant in variants
        }
        resolved = datasets.resolve_installed_dataset("en")
        assert resolved.variant == expected
        assert resolved.path == installed[expected]


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


def test_invalid_sidecar_is_not_listed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEXHINT_DATA_DIR", str(tmp_path / "data"))
    path = datasets._artifact_path("en", "runtime", "2026.08.20")
    path.parent.mkdir(parents=True)
    path.write_bytes(b"not sqlite")
    path.with_name("artifact.json").write_text("{}", encoding="utf-8")

    assert datasets.list_installed_datasets("en") == ()
    with pytest.raises(datasets.DatasetIntegrityError, match="invalid dataset sidecar"):
        datasets._installed_from_sidecar(path)


def test_schema_path_mismatch_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEXHINT_DATA_DIR", str(tmp_path / "data"))
    path = datasets._artifact_path("en", "runtime", "2026.08.20", "7")
    path.parent.mkdir(parents=True)
    path.write_bytes(b"not sqlite")
    path.with_name("artifact.json").write_text(
        '{"language":"en","variant":"runtime","dataset_version":"2026.08.20",'
        '"schema_version":"8","capabilities":["lexical","semantic"]}',
        encoding="utf-8",
    )
    with pytest.raises(datasets.DatasetIntegrityError, match="invalid dataset sidecar"):
        datasets._installed_from_sidecar(path)


def test_explicit_missing_dataset_reports_selector(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LEXHINT_DATA_DIR", str(tmp_path / "data"))
    with pytest.raises(datasets.DatasetNotFound, match="runtime/2026.08.20"):
        datasets.resolve_installed_dataset("en", variant="runtime", version="2026.08.20")
