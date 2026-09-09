from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
from collections.abc import Callable, Iterable, Mapping
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, cast
from urllib.error import HTTPError, URLError

from .download import SUPPORTED_LANGUAGES, cache_dir, data_dir, request
from .languages import normalize_language, supported_base_languages
from .schema import PROFILES
from .schema_contract import SchemaContractError, validate_artifact_structure
from .store import SCHEMA_VERSION

DATASET_REPOSITORY = "buchwandler/lexhint-datasets"
DATASET_CATALOG_URL = (
    "https://raw.githubusercontent.com/buchwandler/lexhint-datasets/main/catalog/datasets-v2.json"
)
DATASET_CATALOG_V1_URL = (
    "https://raw.githubusercontent.com/buchwandler/lexhint-datasets/main/catalog/datasets.json"
)
SUPPORTED_CATALOG_VERSION = 2
SUPPORTED_CATALOG_RUNTIME_CONTRACT = 2
GITHUB_API = "https://api.github.com"
MANIFEST_NAME = "datasets-v2.json"
SUPPORTED_MANIFEST_VERSION = 2
SOURCE_VARIANTS = ("native", "english")
SOURCE_VARIANT_PREFERENCE = ("english", "native")


@dataclass(frozen=True, slots=True)
class DatasetVariantSpec:
    name: str
    capabilities: tuple[str, ...]
    description: str
    recommended: bool = False


DATASET_VARIANTS = {
    "lexical": DatasetVariantSpec(
        "lexical", ("lexical",), "lexical membership/commonness only; smallest"
    ),
    "runtime": DatasetVariantSpec(
        "runtime", PROFILES["runtime"], "lexical + semantic data; recommended default", True
    ),
    "dictionary": DatasetVariantSpec(
        "dictionary",
        ("lexical", "semantic", "dictionary"),
        "lexical + semantic + dictionary data; full dictionary without search indexes",
    ),
    "rich": DatasetVariantSpec(
        "rich",
        PROFILES["rich"],
        "lexical + semantic + dictionary + search data; largest",
    ),
}
DEFAULT_DATASET_VARIANT = next(name for name, spec in DATASET_VARIANTS.items() if spec.recommended)
DATASET_VARIANT_NAMES = tuple(DATASET_VARIANTS)
DEFAULT_VARIANT = DEFAULT_DATASET_VARIANT
VARIANT_CAPABILITIES = {
    name: frozenset(spec.capabilities) for name, spec in DATASET_VARIANTS.items()
}
_SAFE_PART = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+~-]*$")


class DatasetError(RuntimeError):
    """Base class for dataset catalog and installation errors."""


class DatasetCatalogError(DatasetError):
    """The remote release catalog could not be read or parsed."""


class _DatasetCatalogTransportError(DatasetCatalogError):
    """The static dataset catalog could not be fetched."""


class DatasetDownloadError(DatasetError):
    """A dataset asset could not be downloaded."""


class DatasetIntegrityError(DatasetError):
    """A downloaded dataset failed an integrity or metadata check."""


class DatasetNotFound(DatasetError):
    """The requested dataset release or artifact does not exist."""


class DatasetIncompatible(DatasetError):
    """A dataset does not satisfy the installed Lexhint contract."""


class DatasetAmbiguous(DatasetError):
    """Automatic capability selection has more than one maximal result."""


@dataclass(frozen=True, slots=True)
class DatasetProgress:
    downloaded_bytes: int
    total_bytes: int | None
    phase: str


@dataclass(frozen=True, slots=True)
class DatasetArtifact:
    language: str
    variant: str
    dataset_version: str
    release_tag: str
    release_published_at: str
    manifest_version: int
    schema_version: str
    profile: str
    coverage: str
    capabilities: tuple[str, ...]
    compressed_size: int
    uncompressed_size: int
    asset: str
    sha256: str
    download_url: str
    generated_at: str = ""
    source_variant: str = "native"
    wiktionary_edition: str = ""
    metadata_language: str = ""

    def as_dict(self) -> dict[str, object]:
        value = asdict(self)
        value.pop("download_url", None)
        return value


@dataclass(frozen=True, slots=True)
class InstalledDataset:
    language: str
    variant: str
    dataset_version: str
    path: Path
    capabilities: tuple[str, ...]
    schema_version: str
    size_bytes: int
    release_tag: str
    installed_at: str
    release_published_at: str = ""
    asset: str = ""
    sha256: str = ""
    profile: str = ""
    coverage: str = ""
    already_installed: bool = False
    source_variant: str = "native"
    wiktionary_edition: str = ""
    metadata_language: str = ""

    def as_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["path"] = str(self.path)
        return value


@dataclass(frozen=True, slots=True)
class DatasetUpdate:
    language: str
    variant: str
    schema_version: str
    installed_version: str
    available_version: str | None
    path: Path
    update_available: bool
    source_variant: str = "native"

    def as_dict(self) -> dict[str, object]:
        return {
            "language": self.language,
            "source_variant": self.source_variant,
            "variant": self.variant,
            "schema_version": self.schema_version,
            "installed_version": self.installed_version,
            "available_version": self.available_version,
            "path": str(self.path),
            "update_available": self.update_available,
        }


def _preferred_source_variant(
    candidates: Iterable[DatasetArtifact | InstalledDataset],
) -> str:
    for source_variant in SOURCE_VARIANT_PREFERENCE:
        if any(candidate.source_variant == source_variant for candidate in candidates):
            return source_variant
    raise DatasetNotFound("no source variants available")


def _dataset_selector(
    language: str,
    *,
    source_variant: str | None = None,
    variant: str | None = None,
    version: str | None = None,
) -> str:
    parts = [language]
    if source_variant is not None:
        parts.append(source_variant)
    if variant is not None:
        parts.append(variant)
    if version is not None:
        parts.append(version)
    return "/".join(parts)


def _language(language: str) -> str:
    try:
        return normalize_language(language)
    except ValueError as exc:
        raise DatasetNotFound(str(exc)) from exc


def _part(value: str, label: str) -> str:
    if not value or not _SAFE_PART.fullmatch(value):
        raise ValueError(f"invalid dataset {label}: {value!r}")
    return value


def _variant(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in DATASET_VARIANTS:
        raise ValueError(f"unsupported dataset variant {value!r}")
    return normalized


def normalize_source_variant(value: str | None) -> str:
    normalized = (value or "native").strip().lower()
    if normalized not in SOURCE_VARIANTS:
        raise ValueError(f"unsupported dataset source variant {value!r}")
    return normalized


def _artifact_path(
    language: str,
    variant: str,
    version: str,
    schema_version: str = SCHEMA_VERSION,
    source_variant: str = "native",
) -> Path:
    return (
        data_dir()
        / "datasets"
        / _part(_language(language), "language")
        / normalize_source_variant(source_variant)
        / _variant(variant)
        / _part(f"s{schema_version}", "schema")
        / _part(version, "version")
        / "lexhint.sqlite3"
    )


def _sidecar_path(path: Path) -> Path:
    return path.with_name("artifact.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request_json(url: str) -> object:
    try:
        with request(
            url,
            accept="application/vnd.github+json",
            token=os.environ.get("LEXHINT_GITHUB_TOKEN"),
        ) as response:
            return json.load(response)
    except (HTTPError, URLError, OSError, ValueError) as exc:
        raise DatasetCatalogError(f"could not read dataset catalog: {exc}") from exc


_RELEASE_TAG = re.compile(r"^data-(?P<body>.+)$")


def _release_parts(tag: str) -> tuple[str | None, str, str]:
    match = _RELEASE_TAG.fullmatch(tag)
    if match is None:
        return None, "native", tag
    body = match.group("body")
    fields = body.split("-")
    if fields and fields[0] in SUPPORTED_LANGUAGES:
        language = fields[0]
        if len(fields) >= 3 and fields[1] in SOURCE_VARIANTS:
            return language, fields[1], "-".join(fields[2:])
        return language, "native", "-".join(fields[1:])
    return None, "native", body


def _release_identity(tag: str) -> tuple[str | None, str]:
    language, _source_variant, version = _release_parts(tag)
    return language, version


def _release_tag(
    version: str, language: str | None = None, source_variant: str | None = None
) -> str:
    if version.startswith("data-"):
        return version
    normalized_source = normalize_source_variant(source_variant)
    prefix = f"{language}-" if language else ""
    if language and source_variant is not None:
        prefix += f"{normalized_source}-"
    return f"data-{prefix}{version}"


def _release_source_variant(tag: str) -> str:
    return _release_parts(tag)[1]


def _asset_schema_version(asset: str) -> str | None:
    match = re.search(r"-s(?P<schema>[0-9]+)-", asset)
    return match.group("schema") if match else None


def _version_from_tag(tag: str) -> str:
    return _release_identity(tag)[1]


def _catalog_url() -> str:
    return os.environ.get("LEXHINT_DATASET_CATALOG_URL") or DATASET_CATALOG_URL


_CATALOG_CACHE_NAME = "datasets-catalog.json"
_CATALOG_CACHE_METADATA_NAME = "datasets-catalog.json.meta"


def _catalog_cache_path() -> Path:
    return cache_dir() / _CATALOG_CACHE_NAME


def _catalog_cache_metadata_path() -> Path:
    return cache_dir() / _CATALOG_CACHE_METADATA_NAME


def _atomic_cache_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    os.close(temp_fd)
    temp_path = Path(temp_name)
    try:
        temp_path.write_bytes(payload)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _cached_catalog() -> Mapping[str, object]:
    path = _catalog_cache_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise DatasetCatalogError(f"cached dataset catalog is unavailable: {path}") from exc
    if not isinstance(payload, Mapping):
        raise DatasetCatalogError("cached dataset catalog must contain an object")
    _catalog_artifacts(payload)
    return payload


def _catalog_cache_headers() -> dict[str, str]:
    try:
        payload = json.loads(_catalog_cache_metadata_path().read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, Mapping):
        return {}
    return {
        header: str(payload[header])
        for header in ("If-None-Match", "If-Modified-Since")
        if isinstance(payload.get(header), str) and payload[header]
    }


def _fetch_catalog_url(url: str) -> tuple[Mapping[str, object], bytes | None, object]:
    headers = _catalog_cache_headers()
    try:
        with request(
            url,
            accept="application/json",
            token=os.environ.get("LEXHINT_GITHUB_TOKEN"),
            headers=headers,
        ) as response:
            if getattr(response, "status", None) == 304:
                return _cached_catalog(), None, response
            payload_bytes = response.read()
    except HTTPError as exc:
        if exc.code == 304:
            return _cached_catalog(), None, exc
        raise _DatasetCatalogTransportError(f"could not fetch dataset catalog: {exc}") from exc
    except (URLError, OSError) as exc:
        raise _DatasetCatalogTransportError(f"could not fetch dataset catalog: {exc}") from exc
    try:
        payload = json.loads(payload_bytes)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise DatasetCatalogError("dataset catalog is not valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise DatasetCatalogError("dataset catalog must contain an object")
    _catalog_artifacts(payload)
    return payload, payload_bytes, response


def _fetch_catalog() -> Mapping[str, object]:
    urls = [_catalog_url()]
    if "LEXHINT_DATASET_CATALOG_URL" not in os.environ:
        urls.append(DATASET_CATALOG_V1_URL)
    last_error: DatasetError | None = None
    for url in urls:
        try:
            payload, payload_bytes, response = _fetch_catalog_url(url)
        except _DatasetCatalogTransportError as exc:
            last_error = exc
            continue
        if payload_bytes is not None:
            _atomic_cache_write(_catalog_cache_path(), payload_bytes)
            response_headers = getattr(response, "headers", None)
            get_header = getattr(response_headers, "get", lambda _name: None)
            metadata = {
                request_header: value
                for request_header, response_header in (
                    ("If-None-Match", "ETag"),
                    ("If-Modified-Since", "Last-Modified"),
                )
                if isinstance(value := get_header(response_header), str) and value
            }
            _atomic_cache_write(
                _catalog_cache_metadata_path(),
                (json.dumps(metadata, sort_keys=True) + "\n").encode(),
            )
        return payload
    if last_error is not None:
        try:
            return _cached_catalog()
        except DatasetCatalogError as cache_error:
            raise last_error from cache_error
    raise _DatasetCatalogTransportError("could not fetch dataset catalog")


def _catalog_url_for_release(release_tag: str, asset: str) -> str:
    return f"https://github.com/{DATASET_REPOSITORY}/releases/download/{release_tag}/{asset}"


def _catalog_artifact(raw: object, *, catalog_version: int) -> DatasetArtifact:
    if not isinstance(raw, Mapping):
        raise DatasetCatalogError("dataset catalog contains an invalid artifact")
    artifact_id = raw.get("id")
    language_raw = raw.get("language")
    source_variant_raw = raw.get("source_variant", "native")
    wiktionary_edition = raw.get("wiktionary_edition", "")
    metadata_language = raw.get("metadata_language", "")
    variant_raw = raw.get("variant")
    dataset_version = raw.get("dataset_version")
    schema_version = raw.get("schema_version")
    profile = raw.get("profile")
    coverage = raw.get("coverage")
    capabilities_raw = raw.get("capabilities")
    release_tag = raw.get("release_tag")
    release_published_at = raw.get("release_published_at")
    manifest = raw.get("manifest")
    asset = raw.get("asset")
    if (
        not isinstance(artifact_id, str)
        or not artifact_id
        or not isinstance(language_raw, str)
        or not isinstance(variant_raw, str)
        or not isinstance(dataset_version, str)
        or not dataset_version
        or not isinstance(schema_version, str)
        or not schema_version
        or not isinstance(profile, str)
        or not profile
        or not isinstance(coverage, str)
        or coverage != "full"
        or not isinstance(capabilities_raw, list)
        or not isinstance(release_tag, str)
        or not release_tag
        or not isinstance(release_published_at, str)
        or not release_published_at
        or not isinstance(manifest, Mapping)
        or not isinstance(asset, Mapping)
    ):
        raise DatasetCatalogError("dataset catalog artifact is missing required fields")
    if not re.fullmatch(r"[0-9]+", schema_version):
        raise DatasetCatalogError(f"invalid catalog schema version {schema_version!r}")
    try:
        language = _language(language_raw)
    except DatasetNotFound as exc:
        raise DatasetCatalogError(str(exc)) from exc
    try:
        variant = _variant(variant_raw)
        source_variant = normalize_source_variant(source_variant_raw)
    except (TypeError, ValueError) as exc:
        raise DatasetCatalogError(str(exc)) from exc
    if any(not isinstance(item, str) for item in capabilities_raw):
        raise DatasetIncompatible(
            f"catalog artifact {artifact_id!r} declares inconsistent capabilities"
        )
    capabilities = tuple(item for item in capabilities_raw if isinstance(item, str))
    expected_capabilities = DATASET_VARIANTS[variant].capabilities
    if capabilities != expected_capabilities:
        raise DatasetIncompatible(
            f"catalog artifact {artifact_id!r} declares inconsistent capabilities"
        )
    try:
        _part(dataset_version, "version")
    except ValueError as exc:
        raise DatasetCatalogError(str(exc)) from exc
    release_language, release_source_variant, release_version = _release_parts(release_tag)
    if catalog_version == 2 and "source_variant" not in raw:
        raise DatasetCatalogError("catalog v2 artifact is missing source_variant")
    if (
        not release_tag.startswith("data-")
        or release_version != dataset_version
        or (release_language is not None and release_language != language)
        or release_source_variant != source_variant
        or (
            catalog_version == 2
            and release_tag != _release_tag(dataset_version, language, source_variant)
        )
    ):
        raise DatasetCatalogError(
            f"catalog artifact {artifact_id!r} has an inconsistent release tag"
        )
    manifest_url = manifest.get("url")
    manifest_sha256 = manifest.get("sha256")
    asset_name = asset.get("name")
    asset_url = asset.get("url")
    asset_sha256 = asset.get("sha256")
    compressed_size = asset.get("compressed_size")
    uncompressed_size = asset.get("uncompressed_size")
    if not (
        isinstance(manifest_url, str)
        and manifest_url
        and isinstance(manifest_sha256, str)
        and manifest_sha256
        and isinstance(asset_name, str)
        and asset_name
        and isinstance(asset_url, str)
        and asset_url
        and isinstance(asset_sha256, str)
        and asset_sha256
    ):
        raise DatasetCatalogError(f"catalog artifact {artifact_id!r} has invalid URL or hash data")
    if not re.fullmatch(r"[0-9a-f]{64}", manifest_sha256) or not re.fullmatch(
        r"[0-9a-f]{64}", asset_sha256
    ):
        raise DatasetCatalogError(f"catalog artifact {artifact_id!r} has an invalid SHA-256")
    if (
        isinstance(compressed_size, bool)
        or not isinstance(compressed_size, int)
        or compressed_size <= 0
        or isinstance(uncompressed_size, bool)
        or not isinstance(uncompressed_size, int)
        or uncompressed_size <= 0
    ):
        raise DatasetCatalogError(f"catalog artifact {artifact_id!r} has invalid asset sizes")
    asset_prefix = (
        f"lexhint-{language}-{source_variant}-{variant}"
        if catalog_version == 2
        else f"lexhint-{language}-{variant}"
    )
    expected_asset = f"{asset_prefix}-s{schema_version}-{dataset_version}.sqlite3.gz"
    if asset_name != expected_asset:
        raise DatasetCatalogError(
            f"catalog artifact {artifact_id!r} has an inconsistent asset filename"
        )
    if asset_url != _catalog_url_for_release(release_tag, asset_name):
        raise DatasetCatalogError(f"catalog artifact {artifact_id!r} has an inconsistent asset URL")
    if manifest_url != _catalog_url_for_release(release_tag, MANIFEST_NAME):
        raise DatasetCatalogError(
            f"catalog artifact {artifact_id!r} has an inconsistent manifest URL"
        )
    return DatasetArtifact(
        language=language,
        variant=variant,
        source_variant=source_variant,
        wiktionary_edition=str(wiktionary_edition),
        metadata_language=str(metadata_language),
        dataset_version=dataset_version,
        release_tag=release_tag,
        release_published_at=release_published_at,
        manifest_version=SUPPORTED_MANIFEST_VERSION,
        schema_version=schema_version,
        profile=profile,
        coverage=coverage,
        capabilities=capabilities,
        compressed_size=compressed_size,
        uncompressed_size=uncompressed_size,
        asset=asset_name,
        sha256=asset_sha256,
        download_url=asset_url,
    )


def _catalog_artifacts(payload: Mapping[str, object]) -> tuple[DatasetArtifact, ...]:
    catalog_version = payload.get("catalog_version")
    if type(catalog_version) is not int or catalog_version not in {1, 2}:
        raise DatasetCatalogError(f"unsupported dataset catalog version {catalog_version!r}")
    runtime_contract = payload.get("runtime_contract")
    expected_contract = 1 if catalog_version == 1 else 2
    if type(runtime_contract) is not int or runtime_contract != expected_contract:
        raise DatasetCatalogError(f"unsupported dataset runtime contract {runtime_contract!r}")
    if payload.get("repository") != DATASET_REPOSITORY:
        raise DatasetCatalogError("dataset catalog repository does not match Lexhint")
    raw_artifacts = payload.get("artifacts")
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        raise DatasetCatalogError("dataset catalog must contain a non-empty artifacts list")
    result: list[DatasetArtifact] = []
    ids: set[str] = set()
    slots: set[tuple[str, str, str, str, str]] = set()
    for raw in raw_artifacts:
        if not isinstance(raw, Mapping):
            raise DatasetCatalogError("dataset catalog contains an invalid artifact")
        artifact = _catalog_artifact(raw, catalog_version=catalog_version)
        raw_id = raw.get("id")
        if not isinstance(raw_id, str):
            raise DatasetCatalogError("dataset catalog artifact has an invalid id")
        if raw_id in ids:
            raise DatasetCatalogError(f"duplicate dataset catalog artifact id {raw_id!r}")
        ids.add(raw_id)
        slot = (
            artifact.language,
            artifact.source_variant,
            artifact.variant,
            artifact.schema_version,
            artifact.dataset_version,
        )
        if slot in slots:
            raise DatasetCatalogError(f"duplicate dataset catalog artifact slot {slot!r}")
        slots.add(slot)
        result.append(artifact)
    return tuple(result)


def _catalog_remote_artifacts(
    *,
    language: str | None = None,
    version: str | None = None,
    variant: str | None = None,
    source_variant: str | None = None,
    all_compatible: bool = False,
    offline: bool = False,
) -> tuple[DatasetArtifact, ...]:
    payload = _cached_catalog() if offline else _fetch_catalog()
    artifacts = _catalog_artifacts(payload)
    normalized_language = _language(language) if language is not None else None
    requested_version = _version_from_tag(version) if version is not None else None
    selected_variant = _variant(variant) if variant is not None else None
    selected_source_variant = (
        normalize_source_variant(source_variant) if source_variant is not None else None
    )
    matching = tuple(
        artifact
        for artifact in artifacts
        if (normalized_language is None or artifact.language == normalized_language)
        and (requested_version is None or artifact.dataset_version == requested_version)
        and (selected_variant is None or artifact.variant == selected_variant)
        and (selected_source_variant is None or artifact.source_variant == selected_source_variant)
    )
    if version is not None:
        if not matching:
            raise DatasetNotFound("catalog has no requested dataset version")
        compatible = tuple(artifact for artifact in matching if _remote_compatible(artifact))
        if not compatible:
            schemas = ", ".join(sorted({item.schema_version for item in matching}))
            raise DatasetIncompatible(
                f"Dataset {requested_version} uses schema {schemas}; "
                f"this Lexhint requires schema {SCHEMA_VERSION}."
            )
        return tuple(
            sorted(
                compatible,
                key=lambda item: (item.language, item.variant, item.asset),
            )
        )

    compatible = tuple(artifact for artifact in matching if _remote_compatible(artifact))
    if all_compatible:
        return tuple(
            sorted(
                compatible,
                key=lambda item: (item.language, item.variant, item.dataset_version, item.asset),
            )
        )
    if matching and not compatible:
        incompatible_schemas = {
            artifact.schema_version
            for artifact in matching
            if artifact.schema_version != SCHEMA_VERSION
        }
        if incompatible_schemas:
            schemas = ", ".join(sorted(incompatible_schemas))
            requested = normalized_language or "the requested language"
            raise DatasetIncompatible(
                f"No compatible {requested} dataset found for Lexhint schema "
                f"{SCHEMA_VERSION}. Available artifacts use schema {schemas}."
            )
    selected_by_source: dict[tuple[str, str, str], DatasetArtifact] = {}
    for artifact in compatible:
        key = (artifact.language, artifact.source_variant, artifact.variant)
        current = selected_by_source.get(key)
        if current is None or _dataset_order(artifact) > _dataset_order(current):
            selected_by_source[key] = artifact
    if selected_source_variant is not None:
        selected = list(selected_by_source.values())
    else:
        selected_by_language: dict[tuple[str, str], DatasetArtifact] = {}
        for artifact in selected_by_source.values():
            language_key = (artifact.language, artifact.variant)
            current = selected_by_language.get(language_key)
            if (
                current is None
                or (artifact.source_variant == "english" and current.source_variant == "native")
                or (
                    artifact.source_variant == current.source_variant
                    and _dataset_order(artifact) > _dataset_order(current)
                )
            ):
                selected_by_language[language_key] = artifact
        selected = list(selected_by_language.values())
    return tuple(
        sorted(selected, key=lambda item: (item.language, item.source_variant, item.variant))
    )


def _manifest_artifacts(
    release: Mapping[str, object], manifest: Mapping[str, object]
) -> tuple[DatasetArtifact, ...]:
    if manifest.get("manifest_version") != SUPPORTED_MANIFEST_VERSION:
        raise DatasetCatalogError(
            f"unsupported dataset manifest version {manifest.get('manifest_version')!r}"
        )
    tag = str(release.get("tag_name", ""))
    release_language, release_source_variant, release_version = _release_parts(tag)
    manifest_version = str(manifest.get("dataset_version", ""))
    if not tag or release_version != manifest_version:
        raise DatasetCatalogError("dataset manifest version does not match its release tag")
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise DatasetCatalogError("release has no asset list")
    asset_map = {
        str(item.get("name")): item
        for item in assets
        if isinstance(item, Mapping) and item.get("name")
    }
    raw_artifacts = manifest.get("artifacts")
    if not isinstance(raw_artifacts, list):
        raise DatasetCatalogError("dataset manifest has no artifacts")
    if release_language is not None:
        manifest_language = manifest.get("language")
        if manifest_language is not None and manifest_language != release_language:
            raise DatasetCatalogError("dataset manifest language does not match its release tag")
        if any(str(item.get("language", "")) != release_language for item in raw_artifacts):
            raise DatasetCatalogError(
                "language-tagged release contains artifacts for another language"
            )
    result: list[DatasetArtifact] = []
    for raw in raw_artifacts:
        if not isinstance(raw, Mapping):
            raise DatasetCatalogError("dataset manifest contains an invalid artifact")
        language = str(raw.get("language", ""))
        try:
            source_variant = normalize_source_variant(raw.get("source_variant"))
        except (TypeError, ValueError) as exc:
            raise DatasetCatalogError(str(exc)) from exc
        wiktionary_edition = str(raw.get("wiktionary_edition", ""))
        metadata_language = str(raw.get("metadata_language", ""))
        variant = str(raw.get("variant", ""))
        asset = str(raw.get("asset", ""))
        capabilities = raw.get("capabilities")
        if (
            not language
            or not variant
            or not asset
            or not isinstance(capabilities, list)
            or raw.get("format") != "sqlite3-gzip"
        ):
            raise DatasetCatalogError("dataset manifest artifact is missing required fields")
        if source_variant != release_source_variant:
            raise DatasetCatalogError(
                "dataset manifest source variant does not match its release tag"
            )
        if release_source_variant != "native":
            expected_asset = (
                f"lexhint-{language}-{source_variant}-{variant}-"
                f"s{raw.get('schema_version', '')}-{manifest_version}.sqlite3.gz"
            )
            if asset != expected_asset:
                raise DatasetCatalogError(
                    f"dataset artifact {asset!r} has an inconsistent asset filename"
                )
        release_asset = asset_map.get(asset)
        if release_asset is None:
            raise DatasetNotFound(f"release is missing listed dataset asset {asset!r}")
        schema_version = str(raw.get("schema_version", ""))
        asset_schema_version = _asset_schema_version(asset)
        if not schema_version or asset_schema_version != schema_version:
            raise DatasetCatalogError(
                f"dataset artifact {asset!r} has inconsistent schema metadata"
            )
        digest = str(raw.get("sha256", ""))
        download_url = str(release_asset.get("browser_download_url", ""))
        if not digest or not download_url:
            raise DatasetCatalogError(f"dataset artifact {asset!r} has incomplete integrity data")
        result.append(
            DatasetArtifact(
                language=_language(language),
                variant=_variant(variant),
                source_variant=source_variant,
                wiktionary_edition=wiktionary_edition,
                metadata_language=metadata_language,
                dataset_version=manifest_version,
                release_tag=tag,
                release_published_at=str(
                    release.get("published_at") or release.get("created_at") or ""
                ),
                manifest_version=int(str(manifest["manifest_version"])),
                schema_version=schema_version,
                profile=str(raw.get("profile", "")),
                coverage=str(raw.get("coverage", "")),
                capabilities=tuple(str(item) for item in capabilities),
                compressed_size=int(raw.get("compressed_size", 0)),
                uncompressed_size=int(raw.get("uncompressed_size", 0)),
                asset=asset,
                sha256=digest,
                download_url=download_url,
                generated_at=str(manifest.get("generated_at", "")),
            )
        )
    return tuple(result)


def _manifest_for_release(release: Mapping[str, object]) -> tuple[DatasetArtifact, ...]:
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise DatasetCatalogError("release has no asset list")
    manifest_asset = next(
        (
            item
            for item in assets
            if isinstance(item, Mapping) and item.get("name") == MANIFEST_NAME
        ),
        None,
    )
    if manifest_asset is None:
        raise DatasetNotFound(f"release {release.get('tag_name', '')!r} has no {MANIFEST_NAME}")
    url = str(manifest_asset.get("browser_download_url", ""))
    if not url:
        raise DatasetCatalogError("manifest asset has no download URL")
    try:
        with request(url) as response:
            payload = response.read()
    except (HTTPError, URLError, OSError) as exc:
        raise DatasetCatalogError(f"could not download {MANIFEST_NAME}: {exc}") from exc
    digest = str(manifest_asset.get("digest", ""))
    if digest.startswith("sha256:"):
        actual = hashlib.sha256(payload).hexdigest()
        if actual != digest[7:]:
            raise DatasetIntegrityError(f"{MANIFEST_NAME} checksum does not match GitHub metadata")
    try:
        manifest = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise DatasetCatalogError(f"{MANIFEST_NAME} is not valid JSON") from exc
    if not isinstance(manifest, Mapping):
        raise DatasetCatalogError(f"{MANIFEST_NAME} must contain an object")
    return _manifest_artifacts(release, manifest)


def _releases(version: str | None) -> list[Mapping[str, object]]:
    url = f"{GITHUB_API}/repos/{DATASET_REPOSITORY}/releases"
    if version is not None:
        url += f"/tags/{_release_tag(version)}"
    try:
        payload = _request_json(url)
    except DatasetCatalogError as exc:
        if version is not None:
            raise DatasetNotFound(
                f"dataset release {_release_tag(version)!r} was not found"
            ) from exc
        raise
    if version is not None:
        if not isinstance(payload, Mapping):
            raise DatasetNotFound(f"dataset release {_release_tag(version)!r} was not found")
        return [payload]
    if not isinstance(payload, list):
        raise DatasetCatalogError("GitHub releases response is not a list")
    return sorted(
        (
            item
            for item in payload
            if isinstance(item, Mapping)
            and not bool(item.get("draft"))
            and not bool(item.get("prerelease"))
        ),
        key=lambda item: str(item.get("published_at") or item.get("created_at") or ""),
        reverse=True,
    )


def _legacy_remote_artifacts(
    *,
    language: str | None = None,
    version: str | None = None,
    variant: str | None = None,
    source_variant: str | None = None,
) -> tuple[DatasetArtifact, ...]:
    normalized_language = _language(language) if language is not None else None
    requested_version = _version_from_tag(version) if version is not None else None
    if version is None:
        releases = _releases(None)
    elif normalized_language is None:
        releases = [
            release
            for release in _releases(None)
            if _release_identity(str(release.get("tag_name", "")))[1] == requested_version
        ]
    else:
        _parsed_language, parsed_version = _release_identity(version)
        qualified_tag = _release_tag(
            parsed_version,
            normalized_language,
            normalize_source_variant(source_variant),
        )
        try:
            releases = _releases(qualified_tag)
        except DatasetNotFound:
            releases = _releases(_release_tag(parsed_version, normalized_language))
    selected_variant = _variant(variant) if variant is not None else None
    selected_source_variant = (
        normalize_source_variant(source_variant) if source_variant is not None else None
    )
    if not releases:
        raise DatasetNotFound("no published compatible dataset release was found")
    errors: list[DatasetError] = []
    incompatible_schemas: set[str] = set()
    aggregate = normalized_language is None
    aggregated: dict[tuple[str, str, str], DatasetArtifact] = {}
    for release in releases:
        try:
            artifacts = _manifest_for_release(release)
        except DatasetError as exc:
            if version is not None and not aggregate:
                raise
            errors.append(exc)
            continue
        language_items = tuple(
            artifact
            for artifact in artifacts
            if (normalized_language is None or artifact.language == normalized_language)
            and (selected_variant is None or artifact.variant == selected_variant)
            and (
                selected_source_variant is None
                or artifact.source_variant == selected_source_variant
            )
        )
        compatible = tuple(artifact for artifact in language_items if _remote_compatible(artifact))
        incompatible_schemas.update(
            artifact.schema_version
            for artifact in language_items
            if artifact.schema_version != SCHEMA_VERSION
        )
        if aggregate:
            for artifact in compatible:
                key = (artifact.language, artifact.source_variant, artifact.variant)
                current = aggregated.get(key)
                if current is None or _dataset_order(artifact) > _dataset_order(current):
                    aggregated[key] = artifact
            continue
        if compatible:
            return compatible
        if version is not None:
            assert requested_version is not None
            if language_items:
                schemas = ", ".join(sorted({item.schema_version for item in language_items}))
                raise DatasetIncompatible(
                    f"Dataset {requested_version} uses schema {schemas}; "
                    f"this Lexhint requires schema {SCHEMA_VERSION}."
                )
            raise DatasetNotFound(
                f"dataset release {_release_tag(requested_version, normalized_language)} "
                "has no requested language"
            )
    if aggregate and aggregated:
        return tuple(
            sorted(
                aggregated.values(),
                key=lambda item: (item.language, item.source_variant, item.variant),
            )
        )
    if errors:
        raise errors[-1]
    if incompatible_schemas:
        newest = ", ".join(sorted(incompatible_schemas))
        requested = normalized_language or "the requested language"
        raise DatasetIncompatible(
            f"No compatible {requested} dataset found for Lexhint schema {SCHEMA_VERSION}. "
            f"Newest available artifacts use schema {newest}."
        )
    raise DatasetNotFound("no published release contains the requested language")


def _remote_artifacts(
    *,
    language: str | None = None,
    version: str | None = None,
    variant: str | None = None,
    source_variant: str | None = None,
) -> tuple[DatasetArtifact, ...]:
    try:
        return _catalog_remote_artifacts(
            language=language,
            version=version,
            variant=variant,
            source_variant=source_variant,
        )
    except _DatasetCatalogTransportError:
        return _legacy_remote_artifacts(
            language=language,
            version=version,
            variant=variant,
            source_variant=source_variant,
        )
    except DatasetNotFound:
        if version is None:
            raise
        return _legacy_remote_artifacts(
            language=language,
            version=version,
            variant=variant,
            source_variant=source_variant,
        )


def available_datasets(
    *,
    language: str | None = None,
    version: str | None = None,
    variant: str | None = None,
    source_variant: str | None = None,
    offline: bool = False,
) -> tuple[DatasetArtifact, ...]:
    return _catalog_remote_artifacts(
        language=language,
        version=version,
        variant=variant,
        source_variant=source_variant,
        all_compatible=True,
        offline=offline,
    )


def _expected_capabilities(artifact: DatasetArtifact) -> frozenset[str]:
    declared = frozenset(artifact.capabilities)
    known = VARIANT_CAPABILITIES.get(artifact.variant)
    if known is not None and declared != known:
        raise DatasetIncompatible(
            f"artifact {artifact.language}/{artifact.variant} declares inconsistent capabilities"
        )
    return declared


def _remote_compatible(artifact: DatasetArtifact) -> bool:
    if artifact.schema_version != SCHEMA_VERSION or artifact.coverage != "full":
        return False
    try:
        return "lexical" in _expected_capabilities(artifact)
    except DatasetIncompatible:
        return False


def _database_metadata(path: Path) -> dict[str, str]:
    try:
        with closing(sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)) as connection:
            return {
                str(row[0]): str(row[1])
                for row in connection.execute("SELECT key, value FROM metadata")
            }
    except (OSError, sqlite3.DatabaseError) as exc:
        raise DatasetIntegrityError("installed dataset is not a readable SQLite artifact") from exc


def _validate_database_structure(path: Path, capabilities: tuple[str, ...]) -> None:
    try:
        with closing(sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)) as connection:
            validate_artifact_structure(connection, capabilities)
    except (OSError, sqlite3.DatabaseError, SchemaContractError) as exc:
        raise DatasetIntegrityError(
            f"dataset database does not satisfy schema {SCHEMA_VERSION}: {exc}"
        ) from exc


def _installed_from_sidecar(path: Path) -> InstalledDataset:
    sidecar = _sidecar_path(path)
    try:
        raw = json.loads(sidecar.read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping):
            raise ValueError("sidecar is not an object")
        capabilities_raw = raw["capabilities"]
        if not isinstance(capabilities_raw, list):
            raise ValueError("sidecar capabilities are not a list")
        schema_version = str(raw["schema_version"])
        if path.parent.parent.name != f"s{schema_version}":
            raise ValueError("dataset schema path does not match its sidecar")
        return InstalledDataset(
            source_variant=normalize_source_variant(raw.get("source_variant")),
            wiktionary_edition=str(raw.get("wiktionary_edition", "")),
            metadata_language=str(raw.get("metadata_language", "")),
            language=_language(str(raw["language"])),
            variant=_variant(str(raw["variant"])),
            dataset_version=_part(str(raw["dataset_version"]), "version"),
            path=path,
            capabilities=tuple(str(item) for item in capabilities_raw),
            schema_version=schema_version,
            size_bytes=path.stat().st_size,
            release_tag=str(raw.get("release_tag", "")),
            installed_at=str(raw.get("installed_at", "")),
            release_published_at=str(raw.get("release_published_at", "")),
            asset=str(raw.get("asset", "")),
            sha256=str(raw.get("asset_sha256", "")),
            profile=str(raw.get("profile", "")),
            coverage=str(raw.get("coverage", "")),
        )
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
        raise DatasetIntegrityError(f"invalid dataset sidecar {sidecar}") from exc


def validate_installed_dataset(dataset: InstalledDataset) -> InstalledDataset:
    if not dataset.path.is_file():
        raise DatasetIntegrityError(f"dataset database is missing: {dataset.path}")
    metadata = _database_metadata(dataset.path)
    actual_capabilities = tuple(
        item for item in metadata.get("capabilities", "").split(",") if item
    )
    if metadata.get("language") != dataset.language:
        raise DatasetIntegrityError("dataset language metadata does not match its sidecar")
    if metadata.get("dictionary_source_variant") not in {None, "", dataset.source_variant}:
        raise DatasetIntegrityError("dataset source variant does not match its sidecar")
    if metadata.get("schema_version") != dataset.schema_version:
        raise DatasetIntegrityError("dataset schema does not match its sidecar")
    if metadata.get("schema_version") != SCHEMA_VERSION:
        raise DatasetIncompatible(
            f"dataset uses schema {metadata.get('schema_version', 'unknown')}"
        )
    if metadata.get("coverage") != "full" or dataset.coverage != "full":
        raise DatasetIncompatible("dataset does not provide full coverage")
    if "lexical" not in actual_capabilities:
        raise DatasetIncompatible("dataset does not provide lexical capability")
    if actual_capabilities != dataset.capabilities:
        raise DatasetIntegrityError("dataset capabilities do not match its sidecar")
    _validate_database_structure(dataset.path, actual_capabilities)
    return dataset


def _installed_sort_key(item: InstalledDataset) -> tuple[str, int, str, str, str, str]:
    source_rank = {source: index for index, source in enumerate(SOURCE_VARIANTS)}
    return (
        item.language,
        source_rank[item.source_variant],
        item.variant,
        item.schema_version,
        item.dataset_version,
        str(item.path),
    )


def list_installed_datasets(language: str | None = None) -> tuple[InstalledDataset, ...]:
    root = data_dir() / "datasets"
    if not root.is_dir():
        return ()
    languages = [_language(language)] if language is not None else sorted(SUPPORTED_LANGUAGES)
    result: list[InstalledDataset] = []
    for lang in languages:
        lang_root = root / lang
        if not lang_root.is_dir():
            continue
        for path in lang_root.glob("*/ **/lexhint.sqlite3".replace(" ", "")):
            try:
                result.append(validate_installed_dataset(_installed_from_sidecar(path)))
            except DatasetError:
                continue
    return tuple(sorted(result, key=_installed_sort_key))


def _release_key(dataset: InstalledDataset) -> tuple[str, str, str]:
    return (dataset.release_published_at, dataset.installed_at, dataset.dataset_version)


def resolve_installed_dataset(
    language: str,
    *,
    variant: str | None = None,
    version: str | None = None,
    source_variant: str | None = None,
) -> InstalledDataset:
    normalized = _language(language)
    if variant is not None:
        variant = _variant(variant)
    if source_variant is not None:
        source_variant = normalize_source_variant(source_variant)
    candidates: list[InstalledDataset] = []
    all_candidates = list_installed_datasets(normalized)
    for candidate in all_candidates:
        if variant is not None and candidate.variant != variant:
            continue
        if source_variant is not None and candidate.source_variant != source_variant:
            continue
        if version is not None and candidate.dataset_version != version:
            continue
        candidates.append(candidate)
    if not candidates:
        selector = _dataset_selector(
            normalized,
            source_variant=source_variant,
            variant=variant,
            version=version,
        )
        raise DatasetNotFound(f"no compatible installed dataset for {selector}")
    preferred_source = _preferred_source_variant(candidates)
    candidates = [
        candidate for candidate in candidates if candidate.source_variant == preferred_source
    ]
    maxima = [
        candidate
        for candidate in candidates
        if not any(set(other.capabilities) > set(candidate.capabilities) for other in candidates)
    ]
    maximal_variants = {candidate.variant for candidate in maxima}
    if len(maximal_variants) > 1:
        raise DatasetAmbiguous(
            "multiple installed dataset variants provide incomparable capabilities "
            f"for {normalized}: " + ", ".join(sorted(maximal_variants))
        )
    return max(maxima, key=_release_key)


def _dataset_order(value: InstalledDataset | DatasetArtifact) -> tuple[str, str, str, str]:
    return (
        value.release_published_at,
        value.dataset_version,
        value.release_tag,
        value.asset,
    )


def check_dataset_updates(
    language: str | None = None,
    *,
    variant: str | None = None,
    source_variant: str | None = None,
    offline: bool = False,
) -> tuple[DatasetUpdate, ...]:
    installed = list_installed_datasets(language)
    if variant is not None:
        selected_variant = _variant(variant)
        installed = tuple(item for item in installed if item.variant == selected_variant)
    if source_variant is not None:
        source_variant = normalize_source_variant(source_variant)
        installed = tuple(item for item in installed if item.source_variant == source_variant)
    if not installed:
        return ()
    remote = _catalog_remote_artifacts(
        language=language,
        variant=variant,
        source_variant=source_variant,
        offline=offline,
        all_compatible=True,
    )
    newest_remote = {(item.language, item.source_variant, item.variant): item for item in remote}
    groups: dict[tuple[str, str, str], list[InstalledDataset]] = {}
    for item in installed:
        groups.setdefault((item.language, item.source_variant, item.variant), []).append(item)
    result: list[DatasetUpdate] = []
    for key, values in sorted(groups.items()):
        current = max(values, key=_dataset_order)
        available = newest_remote.get(key)
        available_version = available.dataset_version if available is not None else None
        result.append(
            DatasetUpdate(
                language=current.language,
                variant=current.variant,
                source_variant=current.source_variant,
                schema_version=current.schema_version,
                installed_version=current.dataset_version,
                available_version=available_version,
                path=current.path,
                update_available=available is not None
                and _dataset_order(available) > _dataset_order(current),
            )
        )
    return tuple(result)


def update_datasets(
    language: str | None = None,
    *,
    variant: str | None = None,
    source_variant: str | None = None,
    offline: bool = False,
    progress: Callable[[DatasetProgress], None] | None = None,
) -> tuple[InstalledDataset, ...]:
    statuses = check_dataset_updates(
        language, variant=variant, source_variant=source_variant, offline=offline
    )
    result: list[InstalledDataset] = []
    for status in statuses:
        target_version = status.available_version or status.installed_version
        if status.update_available:
            installed = download_dataset(
                status.language,
                variant=status.variant,
                source_variant=status.source_variant,
                version=target_version,
                offline=offline,
                progress=progress,
            )
        else:
            installed = resolve_installed_dataset(
                status.language,
                variant=status.variant,
                source_variant=status.source_variant,
                version=target_version,
            )
        for old in list_installed_datasets(status.language):
            if (
                old.source_variant == status.source_variant
                and old.variant == status.variant
                and old.dataset_version != target_version
            ):
                remove_dataset(
                    old.language,
                    variant=old.variant,
                    source_variant=old.source_variant,
                    version=old.dataset_version,
                )
        result.append(installed)
    return tuple(result)


def _installed_for_artifact(
    artifact: DatasetArtifact, *, already_installed: bool
) -> InstalledDataset:
    path = _artifact_path(
        artifact.language,
        artifact.variant,
        artifact.dataset_version,
        artifact.schema_version,
        artifact.source_variant,
    )
    return InstalledDataset(
        language=artifact.language,
        variant=artifact.variant,
        dataset_version=artifact.dataset_version,
        path=path,
        capabilities=artifact.capabilities,
        schema_version=artifact.schema_version,
        size_bytes=path.stat().st_size,
        release_tag=artifact.release_tag,
        installed_at=_now(),
        release_published_at=artifact.release_published_at,
        asset=artifact.asset,
        sha256=artifact.sha256,
        profile=artifact.profile,
        coverage=artifact.coverage,
        already_installed=already_installed,
        source_variant=artifact.source_variant,
        wiktionary_edition=artifact.wiktionary_edition,
        metadata_language=artifact.metadata_language,
    )


def _write_sidecar(path: Path, artifact: DatasetArtifact, installed_at: str) -> None:
    payload = {
        "install_format": 1,
        "language": artifact.language,
        "source_variant": artifact.source_variant,
        "wiktionary_edition": artifact.wiktionary_edition,
        "metadata_language": artifact.metadata_language,
        "variant": artifact.variant,
        "dataset_version": artifact.dataset_version,
        "release_tag": artifact.release_tag,
        "release_published_at": artifact.release_published_at,
        "manifest_version": artifact.manifest_version,
        "schema_version": artifact.schema_version,
        "profile": artifact.profile,
        "capabilities": list(artifact.capabilities),
        "coverage": artifact.coverage,
        "asset": artifact.asset,
        "asset_sha256": artifact.sha256,
        "compressed_size": artifact.compressed_size,
        "uncompressed_size": artifact.uncompressed_size,
        "installed_at": installed_at,
        "database": path.name,
        "origin": f"github-release:{DATASET_REPOSITORY}",
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class _DigestReader:
    def __init__(self, source: BinaryIO) -> None:
        self.source = source
        self.digest = hashlib.sha256()
        self.count = 0

    def read(self, size: int = -1) -> bytes:
        chunk = self.source.read(size)
        self.digest.update(chunk)
        self.count += len(chunk)
        return chunk


def download_dataset(
    language: str,
    *,
    variant: str = DEFAULT_VARIANT,
    source_variant: str | None = None,
    version: str | None = None,
    force: bool = False,
    offline: bool = False,
    progress: Callable[[DatasetProgress], None] | None = None,
) -> InstalledDataset:
    if offline:
        raise DatasetDownloadError("dataset downloads are unavailable in offline mode")
    normalized = _language(language)
    variant = _variant(variant)
    source_variant = (
        normalize_source_variant(source_variant) if source_variant is not None else None
    )
    artifacts = _remote_artifacts(
        language=normalized,
        version=version,
        variant=variant,
        source_variant=source_variant,
    )
    matching = list(artifacts)
    if source_variant is None:
        preferred = _preferred_source_variant(matching)
        matching = [item for item in matching if item.source_variant == preferred]
    if not matching:
        selector = _dataset_selector(
            normalized,
            source_variant=source_variant,
            variant=variant,
            version=version,
        )
        raise DatasetNotFound(f"no published dataset for {selector}")
    artifact = matching[0]
    if artifact.schema_version != SCHEMA_VERSION:
        raise DatasetIncompatible(
            f"Dataset {artifact.dataset_version} uses schema {artifact.schema_version}; "
            f"this Lexhint requires schema {SCHEMA_VERSION}."
        )
    _expected_capabilities(artifact)
    final_path = _artifact_path(
        artifact.language,
        artifact.variant,
        artifact.dataset_version,
        artifact.schema_version,
        artifact.source_variant,
    )
    if final_path.is_file() and _sidecar_path(final_path).is_file() and not force:
        try:
            existing = validate_installed_dataset(_installed_from_sidecar(final_path))
        except DatasetError:
            existing = None
        if existing is not None:
            return InstalledDataset(
                **{**asdict(existing), "already_installed": True, "path": existing.path}
            )
    final_path.parent.mkdir(parents=True, exist_ok=True)
    temp_fd, temp_name = tempfile.mkstemp(
        prefix=".lexhint-", suffix=".sqlite3.part", dir=final_path.parent
    )
    os.close(temp_fd)
    db_temp = Path(temp_name)
    sidecar_temp = db_temp.with_name(db_temp.name + ".json")
    try:
        if progress:
            progress(DatasetProgress(0, artifact.compressed_size, "downloading"))
        try:
            with request(artifact.download_url) as response:
                reader = _DigestReader(response)
                with (
                    gzip.GzipFile(fileobj=cast(BinaryIO, reader)) as compressed,
                    db_temp.open("wb") as output,
                ):
                    written = 0
                    while chunk := compressed.read(1024 * 1024):
                        written += len(chunk)
                        if written > artifact.uncompressed_size:
                            raise DatasetIntegrityError("dataset exceeds its manifest size")
                        output.write(chunk)
                        if progress:
                            progress(
                                DatasetProgress(
                                    reader.count, artifact.compressed_size, "downloading"
                                )
                            )
                if reader.digest.hexdigest() != artifact.sha256:
                    raise DatasetIntegrityError(
                        "dataset compressed SHA-256 does not match the manifest"
                    )
                if reader.count != artifact.compressed_size:
                    raise DatasetIntegrityError(
                        "dataset compressed size does not match the manifest"
                    )
                if written != artifact.uncompressed_size:
                    raise DatasetIntegrityError(
                        "dataset uncompressed size does not match the manifest"
                    )
        except (HTTPError, URLError, OSError, EOFError) as exc:
            raise DatasetDownloadError(
                f"could not download dataset asset {artifact.asset!r}: {exc}"
            ) from exc
        metadata = _database_metadata(db_temp)
        capabilities = tuple(item for item in metadata.get("capabilities", "").split(",") if item)
        if metadata.get("language") != artifact.language:
            raise DatasetIntegrityError("dataset language does not match the manifest")
        if metadata.get("dictionary_source_variant") not in {None, "", artifact.source_variant}:
            raise DatasetIntegrityError("dataset source variant does not match the manifest")
        if metadata.get("schema_version") != artifact.schema_version:
            raise DatasetIntegrityError("dataset schema does not match the manifest")
        if metadata.get("coverage") != artifact.coverage:
            raise DatasetIntegrityError("dataset coverage does not match the manifest")
        if capabilities != artifact.capabilities:
            raise DatasetIntegrityError("dataset capabilities do not match the manifest")
        _validate_database_structure(db_temp, capabilities)
        installed_at = _now()
        _write_sidecar(sidecar_temp, artifact, installed_at)
        os.replace(db_temp, final_path)
        os.replace(sidecar_temp, _sidecar_path(final_path))
        if progress:
            progress(
                DatasetProgress(artifact.compressed_size, artifact.compressed_size, "installed")
            )
        return _installed_for_artifact(artifact, already_installed=False)
    except DatasetError:
        raise
    except (OSError, sqlite3.DatabaseError) as exc:
        raise DatasetIntegrityError(f"dataset installation failed: {exc}") from exc
    finally:
        db_temp.unlink(missing_ok=True)
        sidecar_temp.unlink(missing_ok=True)


def remove_dataset(
    language: str,
    *,
    variant: str,
    source_variant: str | None = None,
    version: str | None = None,
) -> tuple[Path, ...]:
    normalized = _language(language)
    variant = _variant(variant)
    if source_variant is None:
        matching = tuple(
            item
            for item in list_installed_datasets(normalized)
            if item.variant == variant and (version is None or item.dataset_version == version)
        )
        sources = {item.source_variant for item in matching}
        if len(sources) > 1:
            raise DatasetAmbiguous(
                "both native and English source variants are installed for "
                f"{_dataset_selector(normalized, variant=variant, version=version)}; "
                "choose -e or -n"
            )
        source_variant = next(iter(sources), "native")
    else:
        source_variant = normalize_source_variant(source_variant)
    roots = [data_dir() / "datasets" / normalized / source_variant / variant]
    if source_variant == "native":
        roots.append(data_dir() / "datasets" / normalized / variant)
    paths: list[Path] = []
    for root in roots:
        if version is not None:
            paths.append(
                root / f"s{SCHEMA_VERSION}" / _part(version, "version") / "lexhint.sqlite3"
            )
        else:
            schema_root = root / f"s{SCHEMA_VERSION}"
            if schema_root.is_dir():
                paths.extend(sorted(schema_root.glob("*/lexhint.sqlite3")))
    removed: list[Path] = []
    for path in paths:
        if path.is_file():
            shutil.rmtree(path.parent)
            removed.append(path)
    for root in roots:
        if root.is_dir() and not any(root.iterdir()):
            root.rmdir()
    return tuple(removed)


def validate_datasets(
    language: str | None = None,
    *,
    variant: str | None = None,
    source_variant: str | None = None,
    version: str | None = None,
) -> tuple[InstalledDataset, ...]:
    root = data_dir() / "datasets"
    if not root.is_dir():
        return ()
    languages = [_language(language)] if language is not None else sorted(SUPPORTED_LANGUAGES)
    result: list[InstalledDataset] = []
    for lang in languages:
        for path in (root / lang).glob("*/**/lexhint.sqlite3"):
            dataset = _installed_from_sidecar(path)
            if variant is not None and dataset.variant != _variant(variant):
                continue
            if source_variant is not None and dataset.source_variant != normalize_source_variant(
                source_variant
            ):
                continue
            if version is not None and dataset.dataset_version != version:
                continue
            result.append(validate_installed_dataset(dataset))
    return tuple(sorted(result, key=_installed_sort_key))


__all__ = [
    "DATASET_REPOSITORY",
    "SOURCE_VARIANTS",
    "normalize_source_variant",
    "DATASET_VARIANTS",
    "DATASET_VARIANT_NAMES",
    "DEFAULT_DATASET_VARIANT",
    "DEFAULT_VARIANT",
    "DatasetAmbiguous",
    "DatasetArtifact",
    "DatasetVariantSpec",
    "DatasetCatalogError",
    "DatasetDownloadError",
    "DatasetError",
    "DatasetIncompatible",
    "DatasetIntegrityError",
    "DatasetNotFound",
    "DatasetProgress",
    "DatasetUpdate",
    "InstalledDataset",
    "check_dataset_updates",
    "available_datasets",
    "download_dataset",
    "update_datasets",
    "list_installed_datasets",
    "remove_dataset",
    "resolve_installed_dataset",
    "validate_datasets",
    "validate_installed_dataset",
    "supported_base_languages",
]
