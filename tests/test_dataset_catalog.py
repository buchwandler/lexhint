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
        2,
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


def test_offline_catalog_is_rejected() -> None:
    with pytest.raises(datasets.DatasetCatalogError, match="offline"):
        datasets.available_datasets(offline=True)
