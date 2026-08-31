from __future__ import annotations

import copy
import gzip
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import pytest

import lexhint.datasets as datasets
from lexhint.builder import build_dictionary
from lexhint.store import SCHEMA_VERSION

FIXTURE = Path(__file__).parent / "fixtures" / "kaikki-mini.jsonl"


class Response(io.BytesIO):
    def __enter__(self) -> Response:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def catalog_record(
    language: str = "en",
    version: str = "2026.08.31",
    schema: str = SCHEMA_VERSION,
    variant: str = "runtime",
    tag: str | None = None,
) -> dict[str, Any]:
    tag = tag or f"data-{language}-{version}"
    asset_name = f"lexhint-{language}-{variant}-s{schema}-{version}.sqlite3.gz"
    return {
        "id": f"{language}/{variant}/s{schema}/{version}",
        "language": language,
        "variant": variant,
        "dataset_version": version,
        "schema_version": schema,
        "profile": variant,
        "coverage": "full",
        "capabilities": list(datasets.DATASET_VARIANTS[variant].capabilities),
        "release_tag": tag,
        "release_published_at": "2026-09-01T00:00:00Z",
        "manifest": {
            "url": datasets._catalog_url_for_release(tag, "datasets-v2.json"),
            "sha256": "b" * 64,
        },
        "asset": {
            "name": asset_name,
            "url": datasets._catalog_url_for_release(tag, asset_name),
            "sha256": "a" * 64,
            "compressed_size": 123,
            "uncompressed_size": 456,
        },
    }


def catalog(*records: dict[str, Any]) -> dict[str, Any]:
    return {
        "catalog_version": 1,
        "runtime_contract": 1,
        "repository": datasets.DATASET_REPOSITORY,
        "artifacts": list(records),
    }


def test_valid_catalog_maps_to_dataset_artifact() -> None:
    result = datasets._catalog_artifacts(catalog(catalog_record()))

    assert result == (
        datasets.DatasetArtifact(
            language="en",
            variant="runtime",
            dataset_version="2026.08.31",
            release_tag="data-en-2026.08.31",
            release_published_at="2026-09-01T00:00:00Z",
            manifest_version=2,
            schema_version="10",
            profile="runtime",
            coverage="full",
            capabilities=("lexical", "semantic"),
            compressed_size=123,
            uncompressed_size=456,
            asset="lexhint-en-runtime-s10-2026.08.31.sqlite3.gz",
            sha256="a" * 64,
            download_url=(
                "https://github.com/buchwandler/lexhint-datasets/releases/download/"
                "data-en-2026.08.31/lexhint-en-runtime-s10-2026.08.31.sqlite3.gz"
            ),
        ),
    )


@pytest.mark.parametrize("field", ["catalog_version", "runtime_contract"])
def test_catalog_rejects_unsupported_top_level_version(field: str) -> None:
    payload = catalog(catalog_record())
    payload[field] = 99
    with pytest.raises(datasets.DatasetCatalogError, match="unsupported"):
        datasets._catalog_artifacts(payload)


def test_catalog_rejects_wrong_repository() -> None:
    payload = catalog(catalog_record())
    payload["repository"] = "someone/else"
    with pytest.raises(datasets.DatasetCatalogError, match="repository"):
        datasets._catalog_artifacts(payload)


def test_catalog_rejects_duplicate_ids_and_slots() -> None:
    first = catalog_record()
    duplicate_id = copy.deepcopy(first)
    with pytest.raises(datasets.DatasetCatalogError, match="duplicate.*id"):
        datasets._catalog_artifacts(catalog(first, duplicate_id))

    duplicate_slot = copy.deepcopy(first)
    duplicate_slot["id"] = "another-id"
    with pytest.raises(datasets.DatasetCatalogError, match="duplicate.*slot"):
        datasets._catalog_artifacts(catalog(first, duplicate_slot))


def test_catalog_rejects_malformed_artifacts_list() -> None:
    payload = catalog(catalog_record())
    payload["artifacts"] = {"not": "a list"}
    with pytest.raises(datasets.DatasetCatalogError, match="artifacts list"):
        datasets._catalog_artifacts(payload)


@pytest.mark.parametrize(
    ("change", "match"),
    [
        (lambda record: record["asset"].update(sha256="A" * 64), "SHA-256"),
        (lambda record: record["manifest"].update(sha256="short"), "SHA-256"),
        (lambda record: record["asset"].update(compressed_size=0), "sizes"),
        (lambda record: record["asset"].update(uncompressed_size=-1), "sizes"),
        (lambda record: record["asset"].update(url="http://example.test/asset"), "URL"),
        (lambda record: record.update(release_tag="data-en-other"), "release tag"),
        (
            lambda record: record["asset"].update(
                name="lexhint-en-runtime-s9-2026.08.31.sqlite3.gz"
            ),
            "filename",
        ),
    ],
)
def test_catalog_rejects_integrity_and_identity_invariants(change: Any, match: str) -> None:
    record = catalog_record()
    change(record)
    with pytest.raises(datasets.DatasetCatalogError, match=match):
        datasets._catalog_artifacts(catalog(record))


def test_catalog_rejects_unsupported_language_and_variant() -> None:
    language = catalog_record(language="xx")
    with pytest.raises(datasets.DatasetCatalogError, match="unsupported"):
        datasets._catalog_artifacts(catalog(language))

    variant = catalog_record()
    variant["variant"] = "unknown"
    with pytest.raises(datasets.DatasetCatalogError, match="unsupported"):
        datasets._catalog_artifacts(catalog(variant))


def test_catalog_rejects_wrong_variant_capabilities() -> None:
    record = catalog_record()
    record["capabilities"] = ["lexical"]
    with pytest.raises(datasets.DatasetIncompatible, match="capabilities"):
        datasets._catalog_artifacts(catalog(record))


def test_catalog_selects_newest_compatible_artifact_per_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = catalog_record(language="de", version="2026.08.20")
    old["release_published_at"] = "2026-08-21T00:00:00Z"
    newer_incompatible = catalog_record(language="de", version="2026.09.01", schema="11")
    newest_compatible = catalog_record(language="de", version="2026.08.31")
    newest_compatible["release_published_at"] = "2026-09-02T00:00:00Z"
    english = catalog_record(language="en", version="2026.08.31")
    monkeypatch.setattr(
        datasets,
        "_fetch_catalog",
        lambda: catalog(old, newer_incompatible, newest_compatible, english),
    )

    result = datasets._catalog_remote_artifacts(language="de", variant="runtime")

    assert len(result) == 1
    assert result[0].dataset_version == "2026.08.31"
    assert result[0].schema_version == SCHEMA_VERSION


def test_catalog_resolver_uses_one_request_and_no_releases_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    records = [catalog_record(language=language) for language in ("de", "en", "es")]
    payload = catalog(*records)
    calls: list[str] = []

    def fake_request(url: str, **kwargs: object) -> Response:
        calls.append(url)
        return Response(json.dumps(payload).encode())

    monkeypatch.setattr(datasets, "request", fake_request)
    monkeypatch.setattr(
        datasets, "_legacy_remote_artifacts", lambda **kwargs: pytest.fail("releases used")
    )

    result = datasets.available_datasets(variant="runtime")

    assert {item.language for item in result} == {"de", "en", "es"}
    assert calls == [datasets.DATASET_CATALOG_URL]


def test_catalog_exact_version_supports_combined_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = catalog_record(language="de", version="2025.01.01", tag="data-2025.01.01")
    monkeypatch.setattr(datasets, "_fetch_catalog", lambda: catalog(record))
    assert datasets._catalog_remote_artifacts(language="de", version="2025.01.01") == (
        datasets._catalog_artifacts(catalog(record))[0],
    )


def test_catalog_exact_version_missing_uses_legacy_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fallback = datasets.DatasetArtifact(
        "en",
        "runtime",
        "2024.01.01",
        "data-2024.01.01",
        "2024-01-02T00:00:00Z",
        2,
        "10",
        "runtime",
        "full",
        ("lexical", "semantic"),
        1,
        1,
        "asset",
        "a" * 64,
        "https://example.test/asset",
    )
    monkeypatch.setattr(datasets, "_fetch_catalog", lambda: catalog(catalog_record()))
    monkeypatch.setattr(datasets, "_legacy_remote_artifacts", lambda **kwargs: (fallback,))

    assert datasets._remote_artifacts(language="en", version="2024.01.01") == (fallback,)


def test_catalog_transport_failure_uses_legacy_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        datasets,
        "_fetch_catalog",
        lambda: (_ for _ in ()).throw(datasets._DatasetCatalogTransportError("unavailable")),
    )
    monkeypatch.setattr(datasets, "_legacy_remote_artifacts", lambda **kwargs: ())
    assert datasets._remote_artifacts(language="en") == ()


def test_catalog_corruption_does_not_use_legacy_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(datasets, "_fetch_catalog", lambda: {"catalog_version": 99})
    monkeypatch.setattr(
        datasets, "_legacy_remote_artifacts", lambda **kwargs: pytest.fail("fallback used")
    )
    with pytest.raises(datasets.DatasetCatalogError, match="unsupported"):
        datasets._remote_artifacts(language="en")


def test_offline_catalog_access_uses_cache_without_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("LEXHINT_CACHE_DIR", str(tmp_path))
    datasets._atomic_cache_write(
        datasets._catalog_cache_path(),
        json.dumps(catalog(catalog_record())).encode(),
    )
    monkeypatch.setattr(datasets, "request", lambda *args, **kwargs: pytest.fail("network used"))
    result = datasets.available_datasets(offline=True)
    assert len(result) == 1

def test_catalog_artifact_installs_through_existing_integrity_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LEXHINT_DATA_DIR", str(tmp_path / "data"))
    source, _ = build_dictionary(
        "en", FIXTURE, output=tmp_path / "source.sqlite3", capabilities="lexical", no_frequency=True
    )
    database = source.read_bytes()
    compressed = gzip.compress(database)
    record = catalog_record(variant="lexical")
    record["asset"]["compressed_size"] = len(compressed)
    record["asset"]["uncompressed_size"] = len(database)
    record["asset"]["sha256"] = hashlib.sha256(compressed).hexdigest()
    payload = catalog(record)

    def fake_request(url: str, **kwargs: object) -> Response:
        body = json.dumps(payload).encode() if url == datasets.DATASET_CATALOG_URL else compressed
        return Response(body)

    monkeypatch.setattr(datasets, "request", fake_request)
    installed = datasets.download_dataset("en", variant="lexical")

    assert installed.path.read_bytes() == database
    assert installed.sha256 == record["asset"]["sha256"]
