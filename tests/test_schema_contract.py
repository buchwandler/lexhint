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
from lexhint.schema_contract import (
    SCHEMA_CONTRACT,
    SQLITE_APPLICATION_ID,
    SQLITE_USER_VERSION,
    SchemaContractError,
    inspect_schema,
    validate_artifact_structure,
)
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
    def catalog_unavailable(**kwargs: object) -> None:
        raise datasets._DatasetCatalogTransportError("test")

    monkeypatch.setattr(datasets, "_catalog_remote_artifacts", catalog_unavailable)
    newer = artifact("2026.10.01", "11")
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
    def catalog_unavailable(**kwargs: object) -> None:
        raise datasets._DatasetCatalogTransportError("test")

    monkeypatch.setattr(datasets, "_catalog_remote_artifacts", catalog_unavailable)
    incompatible = artifact("2026.10.15", "7")
    monkeypatch.setattr(
        datasets,
        "_releases",
        lambda version: [{"tag_name": incompatible.release_tag}],
    )
    monkeypatch.setattr(datasets, "_manifest_for_release", lambda release: (incompatible,))
    with pytest.raises(datasets.DatasetIncompatible, match="requires schema 10"):
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


def test_search_tables_are_capability_gated() -> None:
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


@pytest.mark.parametrize(
    ("profile", "capabilities"),
    (
        ("lexical", ("lexical",)),
        ("runtime", PROFILES["runtime"]),
        ("dictionary", ("lexical", "semantic", "dictionary")),
        ("rich", PROFILES["rich"]),
    ),
)
def test_schema10_contract_is_frozen(profile: str, capabilities: tuple[str, ...]) -> None:
    connection = sqlite3.connect(":memory:")
    try:
        create_schema(connection, capabilities)
        validate_artifact_structure(connection, capabilities)
        assert set(inspect_schema(connection)) == set(SCHEMA_CONTRACT[profile].tables)
    finally:
        connection.close()


def test_schema10_contract_rejects_required_column_change() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        create_schema(connection, ("lexical",))
        connection.execute("ALTER TABLE lexemes RENAME COLUMN word TO token")
        with pytest.raises(SchemaContractError, match="bump SCHEMA_VERSION"):
            validate_artifact_structure(connection, ("lexical",))
    finally:
        connection.close()


def test_schema10_contract_rejects_missing_table_and_index() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        create_schema(connection, PROFILES["runtime"])
        connection.execute("DROP TABLE lexeme_domains")
        with pytest.raises(SchemaContractError, match="tables"):
            validate_artifact_structure(connection, PROFILES["runtime"])
    finally:
        connection.close()

    connection = sqlite3.connect(":memory:")
    try:
        create_schema(connection, ("lexical",))
        connection.execute("DROP INDEX lexemes_corpus_rank_idx")
        with pytest.raises(SchemaContractError, match="lexemes_corpus_rank_idx"):
            validate_artifact_structure(connection, ("lexical",))
    finally:
        connection.close()


def test_schema10_contract_rejects_primary_key_and_without_rowid_changes() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        create_schema(connection, ("lexical",))
        connection.execute("DROP TABLE lexemes")
        connection.execute(
            "CREATE TABLE lexemes (word TEXT, entry_count INTEGER NOT NULL, "
            "has_lowercase INTEGER NOT NULL, has_titlecase INTEGER NOT NULL, "
            "has_uppercase INTEGER NOT NULL, corpus_count INTEGER, corpus_rank INTEGER)"
        )
        with pytest.raises(SchemaContractError, match="primary_key"):
            validate_artifact_structure(connection, ("lexical",))
    finally:
        connection.close()

    connection = sqlite3.connect(":memory:")
    try:
        create_schema(connection, PROFILES["dictionary"])
        connection.execute("DROP TABLE sense_topics")
        connection.execute(
            "CREATE TABLE sense_topics (topic TEXT NOT NULL, sense_id INTEGER NOT NULL, "
            "PRIMARY KEY (topic, sense_id), "
            "FOREIGN KEY(sense_id) REFERENCES senses(id) ON DELETE CASCADE)"
        )
        with pytest.raises(SchemaContractError, match="without_rowid"):
            validate_artifact_structure(connection, PROFILES["dictionary"])
    finally:
        connection.close()


def test_sqlite_header_identity_constants_are_schema10_specific() -> None:
    assert SQLITE_APPLICATION_ID == 0x4C584831
    assert SQLITE_USER_VERSION == 10
