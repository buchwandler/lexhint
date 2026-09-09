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
    source_variant: str = "native",
    release_published_at: str = "2026-08-21T00:00:00Z",
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
    target = datasets._artifact_path("en", variant, version, source_variant=source_variant)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
    artifact = datasets.DatasetArtifact(
        "en",
        variant,
        version,
        f"data-{version}",
        release_published_at,
        2,
        "10",
        capabilities[1],
        "full",
        tuple(capabilities[0].split(",")),
        1,
        target.stat().st_size,
        target.name,
        "fixture",
        "",
        source_variant=source_variant,
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


def test_source_variants_coexist_and_resolve_english_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    native = install_fixture(tmp_path, monkeypatch, "runtime", source_variant="native")
    english = install_fixture(tmp_path, monkeypatch, "runtime", source_variant="english")
    assert native != english
    assert "native" in native.parts
    assert "english" in english.parts
    assert datasets.resolve_installed_dataset("en").path == english
    assert Lexicon("en").path == english
    assert Lexicon("en", source_variant="native").path == native
    assert datasets.remove_dataset("en", variant="runtime", source_variant="english") == (english,)


def test_selectors_preserve_english_preference_and_capability_ranking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    native = install_fixture(
        tmp_path,
        monkeypatch,
        "runtime",
        source_variant="native",
        release_published_at="2026-09-02T00:00:00Z",
    )
    english = install_fixture(
        tmp_path,
        monkeypatch,
        "runtime",
        source_variant="english",
        release_published_at="2026-09-01T00:00:00Z",
    )
    assert datasets.resolve_installed_dataset("en", variant="runtime").path == english
    assert native.exists()

    version = "2026.09.01"
    install_fixture(tmp_path, monkeypatch, "runtime", version, source_variant="native")
    english_version = install_fixture(
        tmp_path, monkeypatch, "runtime", version, source_variant="english"
    )
    assert datasets.resolve_installed_dataset("en", version=version).path == english_version

    rich = install_fixture(tmp_path, monkeypatch, "rich", "2026.09.02", source_variant="english")
    install_fixture(tmp_path, monkeypatch, "lexical", "2026.09.03", source_variant="english")
    assert datasets.resolve_installed_dataset("en", source_variant="english").path == rich

    capability_version = "2026.09.04"
    for variant in ("lexical", "runtime", "dictionary", "rich"):
        install_fixture(
            tmp_path,
            monkeypatch,
            variant,
            capability_version,
            source_variant="english",
        )
    assert datasets.resolve_installed_dataset("en", version=capability_version).variant == "rich"


def test_single_source_is_selected_automatically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    native_root = tmp_path / "native-only"
    native = install_fixture(native_root, monkeypatch, "runtime", source_variant="native")
    assert datasets.resolve_installed_dataset("en").path == native

    english_root = tmp_path / "english-only"
    english = install_fixture(english_root, monkeypatch, "runtime", source_variant="english")
    assert datasets.resolve_installed_dataset("en").path == english


def test_remove_selects_only_source_and_rejects_ambiguity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    native = install_fixture(tmp_path, monkeypatch, "runtime", source_variant="native")
    assert datasets.remove_dataset("en", variant="runtime") == (native,)

    english = install_fixture(tmp_path, monkeypatch, "runtime", source_variant="english")
    assert datasets.remove_dataset("en", variant="runtime") == (english,)

    native = install_fixture(tmp_path, monkeypatch, "runtime", source_variant="native")
    english = install_fixture(tmp_path, monkeypatch, "runtime", source_variant="english")
    assert native.exists() and english.exists()
    with pytest.raises(datasets.DatasetAmbiguous, match="choose -e or -n"):
        datasets.remove_dataset("en", variant="runtime")


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


def test_inventory_and_validation_order_include_source_variant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    english_runtime = install_fixture(tmp_path, monkeypatch, "runtime", source_variant="english")
    native_rich = install_fixture(tmp_path, monkeypatch, "rich", source_variant="native")
    native_runtime = install_fixture(tmp_path, monkeypatch, "runtime", source_variant="native")

    expected = [native_rich, native_runtime, english_runtime]
    assert [item.path for item in datasets.list_installed_datasets("en")] == expected
    assert [item.path for item in datasets.validate_datasets("en")] == expected
