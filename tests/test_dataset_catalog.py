from __future__ import annotations

import pytest

import lexhint.datasets as datasets


def test_manifest_parsing_preserves_release_metadata() -> None:
    release = {
        "tag_name": "data-2026.08.20",
        "published_at": "2026-08-21T06:06:00Z",
        "assets": [
            {
                "name": "lexhint-en-runtime-s7-2026.08.20.sqlite3.gz",
                "browser_download_url": "https://example.test/runtime.gz",
            }
        ],
    }
    manifest = {
        "manifest_version": 2,
        "dataset_version": "2026.08.20",
        "generated_at": "2026-08-21T05:00:00Z",
        "artifacts": [
            {
                "language": "en",
                "variant": "runtime",
                "profile": "runtime",
                "capabilities": ["lexical", "semantic"],
                "coverage": "full",
                "schema_version": "7",
                "format": "sqlite3-gzip",
                "asset": "lexhint-en-runtime-s7-2026.08.20.sqlite3.gz",
                "sha256": "a" * 64,
                "compressed_size": 12,
                "uncompressed_size": 34,
            }
        ],
    }
    result = datasets._manifest_artifacts(release, manifest)
    assert result[0].release_tag == "data-2026.08.20"
    assert result[0].download_url.endswith("runtime.gz")
    assert result[0].capabilities == ("lexical", "semantic")


def test_inconsistent_variant_capabilities_are_not_remote_compatible() -> None:
    artifact = datasets.DatasetArtifact(
        "en",
        "runtime",
        "2026.08.20",
        "data-2026.08.20",
        "",
        "10",
        "7",
        "runtime",
        "full",
        ("lexical",),
        1,
        1,
        "asset",
        "a" * 64,
        "https://example.test/asset",
    )
    assert not datasets._remote_compatible(artifact)

def test_offline_catalog_without_cache_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setenv("LEXHINT_CACHE_DIR", str(tmp_path))
    with pytest.raises(datasets.DatasetCatalogError, match="cached dataset catalog"):
        datasets.available_datasets(offline=True)

def test_managed_dataset_variants_match_named_profiles() -> None:
    from lexhint.schema import PROFILES

    assert datasets.DATASET_VARIANTS["runtime"].capabilities == PROFILES["runtime"]
    assert datasets.DATASET_VARIANTS["rich"].capabilities == PROFILES["rich"]


def test_rich_search_artifact_contract() -> None:
    artifact = datasets.DatasetArtifact(
        "en",
        "rich",
        "2026.08.20",
        "data-2026.08.20",
        "2026-08-21T00:00:00Z",
        2,
        "10",
        "rich",
        "full",
        ("lexical", "semantic", "dictionary", "search"),
        1,
        1,
        "lexhint-en-rich-s10-2026.08.20.sqlite3.gz",
        "a" * 64,
        "https://example.test/asset",
    )

    assert datasets._remote_compatible(artifact)


def test_dictionary_artifact_contract_without_search() -> None:
    artifact = datasets.DatasetArtifact(
        "en",
        "dictionary",
        "2026.08.20",
        "data-2026.08.20",
        "2026-08-21T00:00:00Z",
        2,
        "10",
        "custom",
        "full",
        ("lexical", "semantic", "dictionary"),
        1,
        1,
        "lexhint-en-dictionary-s10-2026.08.20.sqlite3.gz",
        "a" * 64,
        "https://example.test/asset",
    )
    assert datasets._remote_compatible(artifact)

    inconsistent = datasets.DatasetArtifact(
        "en",
        "dictionary",
        "2026.08.20",
        "data-2026.08.20",
        "2026-08-21T00:00:00Z",
        2,
        "8",
        "custom",
        "full",
        ("lexical", "semantic", "dictionary", "search"),
        1,
        1,
        "lexhint-en-dictionary-s8-2026.08.20.sqlite3.gz",
        "a" * 64,
        "https://example.test/asset",
    )
    assert not datasets._remote_compatible(inconsistent)


def test_manifest_rejects_unsupported_version() -> None:
    with pytest.raises(datasets.DatasetCatalogError, match="unsupported"):
        datasets._manifest_artifacts({"tag_name": "data-1", "assets": []}, {"manifest_version": 1})


def test_manifest_rejects_missing_assets() -> None:
    with pytest.raises(datasets.DatasetCatalogError, match="asset list"):
        datasets._manifest_artifacts(
            {"tag_name": "data-1"}, {"manifest_version": 2, "dataset_version": "1"}
        )


def test_manifest_rejects_missing_manifest_artifact() -> None:
    release = {"tag_name": "data-1", "assets": []}
    manifest = {"manifest_version": 2, "dataset_version": "1", "artifacts": [None]}
    with pytest.raises(datasets.DatasetCatalogError, match="invalid artifact"):
        datasets._manifest_artifacts(release, manifest)


def test_manifest_rejects_unlisted_asset() -> None:
    release = {"tag_name": "data-1", "assets": []}
    manifest = {
        "manifest_version": 2,
        "dataset_version": "1",
        "artifacts": [{"language": "en", "variant": "runtime", "asset": "missing"}],
    }
    with pytest.raises(datasets.DatasetCatalogError, match="missing required fields"):
        datasets._manifest_artifacts(release, manifest)


def test_manifest_rejects_missing_release_asset() -> None:
    release = {"tag_name": "data-1", "assets": []}
    manifest = {
        "manifest_version": 2,
        "dataset_version": "1",
        "artifacts": [
            {
                "language": "en",
                "variant": "runtime",
                "profile": "runtime",
                "capabilities": ["lexical", "semantic"],
                "coverage": "full",
                "schema_version": "8",
                "format": "sqlite3-gzip",
                "asset": "lexhint-en-runtime-s8-1.sqlite3.gz",
            }
        ],
    }
    with pytest.raises(datasets.DatasetNotFound, match="missing listed"):
        datasets._manifest_artifacts(release, manifest)


def test_release_identity_supports_legacy_and_language_tags() -> None:
    assert datasets._release_identity("data-2026.08.25") == (None, "2026.08.25")
    assert datasets._release_identity("data-de-2026.08.31") == ("de", "2026.08.31")
    assert datasets._version_from_tag("data-de-2026.08.31") == "2026.08.31"


def _language_manifest_release(
    language: str, tag: str
) -> tuple[dict[str, object], dict[str, object]]:
    asset = f"lexhint-{language}-runtime-s10-v1.sqlite3.gz"
    release = {
        "tag_name": tag,
        "assets": [{"name": asset, "browser_download_url": "https://example.test/asset"}],
    }
    manifest = {
        "manifest_version": 2,
        "dataset_version": "2026.08.31",
        "language": language,
        "artifacts": [
            {
                "language": language,
                "variant": "runtime",
                "profile": "runtime",
                "capabilities": ["lexical", "semantic"],
                "coverage": "full",
                "schema_version": "10",
                "format": "sqlite3-gzip",
                "asset": asset,
                "sha256": "a" * 64,
                "compressed_size": 1,
                "uncompressed_size": 1,
            }
        ],
    }
    return release, manifest


def test_language_tag_manifest_is_checked_against_artifact_languages() -> None:
    release, manifest = _language_manifest_release("de", "data-de-2026.08.31")
    assert datasets._manifest_artifacts(release, manifest)[0].language == "de"

    mixed_release, mixed_manifest = _language_manifest_release("de", "data-de-2026.08.31")
    mixed_manifest["artifacts"] = [
        *mixed_manifest["artifacts"],
        {**mixed_manifest["artifacts"][0], "language": "es"},
    ]
    with pytest.raises(datasets.DatasetCatalogError, match="another language"):
        datasets._manifest_artifacts(mixed_release, mixed_manifest)
