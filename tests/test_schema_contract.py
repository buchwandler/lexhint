from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import lexhint.datasets as datasets
from lexhint import (
    DATASET_VARIANT_NAMES,
    DATASET_VARIANTS,
    DEFAULT_DATASET_VARIANT,
    SCHEMA_VERSION,
    supported_base_languages,
)
from lexhint.schema import PROFILES, normalize_capabilities
from lexhint.store import create_schema


def artifact(version: str, schema: str) -> datasets.DatasetArtifact:
    return datasets.DatasetArtifact(
        "en",
        "runtime",
        version,
        f"data-{version}",
        "",
        2,
        schema,
        "runtime",
        "full",
        ("lexical", "semantic"),
        1,
        1,
        f"lexhint-en-runtime-s{schema}-{version}.sqlite3.gz",
        "a" * 64,
        "https://example.test/asset",
    )


def test_public_contract_is_single_and_importable() -> None:
    assert DATASET_VARIANT_NAMES == ("lexical", "runtime", "dictionary", "rich")
    assert tuple(DATASET_VARIANTS) == DATASET_VARIANT_NAMES
    assert DEFAULT_DATASET_VARIANT == "runtime"
    assert supported_base_languages() == ("cs", "de", "en", "es", "fr", "it", "pt")


def test_public_dataset_variants_match_named_profiles() -> None:
    assert DATASET_VARIANTS["runtime"].capabilities == PROFILES["runtime"]
    assert DATASET_VARIANTS["dictionary"].capabilities == (
        "lexical",
        "semantic",
        "dictionary",
    )
    assert DATASET_VARIANTS["rich"].capabilities == PROFILES["rich"]


def test_remote_resolution_filters_schema_before_ranking(monkeypatch: pytest.MonkeyPatch) -> None:
    newer = artifact("2026.10.01", "10")
    compatible = artifact("2026.09.01", SCHEMA_VERSION)
    releases = [{"tag_name": newer.release_tag}, {"tag_name": compatible.release_tag}]
    monkeypatch.setattr(datasets, "_releases", lambda version: releases)
    monkeypatch.setattr(
        datasets,
        "_manifest_for_release",
        lambda release: (newer,) if release["tag_name"] == newer.release_tag else (compatible,),
    )
    assert datasets._remote_artifacts(language="en", variant="runtime") == (compatible,)


def test_explicit_schema_mismatch_does_not_fall_back(monkeypatch: pytest.MonkeyPatch) -> None:
    incompatible = artifact("2026.10.15", "7")
    monkeypatch.setattr(
        datasets,
        "_releases",
        lambda version: [{"tag_name": incompatible.release_tag}],
    )
    monkeypatch.setattr(datasets, "_manifest_for_release", lambda release: (incompatible,))
    with pytest.raises(datasets.DatasetIncompatible, match="requires schema 9"):
        datasets._remote_artifacts(language="en", variant="runtime", version="2026.10.15")


def test_schema_is_part_of_artifact_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEXHINT_DATA_DIR", str(tmp_path))
    s7 = datasets._artifact_path("en", "runtime", "2026.09.01", "7")
    s8 = datasets._artifact_path("en", "runtime", "2026.10.15", "8")
    assert s7 != s8
    assert s7.parent.parent.name == "s7"
    assert s8.parent.parent.name == "s8"


def test_manifest_requires_filename_and_manifest_schema_agreement() -> None:
    release = {
        "tag_name": "data-2026.08.20",
        "assets": [
            {"name": "lexhint-en-runtime-s8-2026.08.20.sqlite3.gz", "browser_download_url": "x"}
        ],
    }
    manifest = {
        "manifest_version": 2,
        "dataset_version": "2026.08.20",
        "artifacts": [
            {
                "language": "en",
                "variant": "runtime",
                "schema_version": "7",
                "profile": "runtime",
                "capabilities": ["lexical", "semantic"],
                "coverage": "full",
                "format": "sqlite3-gzip",
                "asset": "lexhint-en-runtime-s8-2026.08.20.sqlite3.gz",
                "sha256": "a" * 64,
                "compressed_size": 1,
                "uncompressed_size": 1,
            }
        ],
    }
    with pytest.raises(datasets.DatasetCatalogError, match="inconsistent schema"):
        datasets._manifest_artifacts(release, manifest)


def test_schema_8_search_tables_are_capability_gated() -> None:
    def tables(capabilities: str) -> set[str]:
        connection = sqlite3.connect(":memory:")
        selection = (
            normalize_capabilities(profile="rich")
            if capabilities == "rich"
            else normalize_capabilities(capabilities)
        )
        create_schema(connection, selection.capabilities)
        result = {
            str(row[0])
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        connection.close()
        return result

    lexical = tables("lexical")
    lexical_search = tables("lexical,search")
    rich = tables("rich")
    assert "lexeme_ngrams" not in lexical
    assert "sense_search_terms" not in lexical
    assert "lexeme_ngrams" in lexical_search
    assert "sense_search_terms" not in lexical_search
    assert {"lexeme_ngrams", "sense_search_terms"} <= rich
