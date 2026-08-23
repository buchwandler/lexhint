from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
from collections.abc import Callable, Mapping
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, cast
from urllib.error import HTTPError, URLError

from .download import SUPPORTED_LANGUAGES, data_dir, request
from .languages import normalize_language, supported_base_languages
from .schema import PROFILES
from .store import SCHEMA_VERSION

DATASET_REPOSITORY = "buchwandler/lexhint-datasets"
GITHUB_API = "https://api.github.com"
MANIFEST_NAME = "datasets-v2.json"
SUPPORTED_MANIFEST_VERSION = 2


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

    def as_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["path"] = str(self.path)
        return value


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


def _artifact_path(
    language: str,
    variant: str,
    version: str,
    schema_version: str = SCHEMA_VERSION,
) -> Path:
    return (
        data_dir()
        / "datasets"
        / _part(_language(language), "language")
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


def _release_tag(version: str) -> str:
    return version if version.startswith("data-") else f"data-{version}"


def _asset_schema_version(asset: str) -> str | None:
    match = re.search(r"-s(?P<schema>[0-9]+)-", asset)
    return match.group("schema") if match else None


def _version_from_tag(tag: str) -> str:
    return tag[5:] if tag.startswith("data-") else tag


def _manifest_artifacts(
    release: Mapping[str, object], manifest: Mapping[str, object]
) -> tuple[DatasetArtifact, ...]:
    if manifest.get("manifest_version") != SUPPORTED_MANIFEST_VERSION:
        raise DatasetCatalogError(
            f"unsupported dataset manifest version {manifest.get('manifest_version')!r}"
        )
    tag = str(release.get("tag_name", ""))
    manifest_version = str(manifest.get("dataset_version", ""))
    if not tag or _version_from_tag(tag) != manifest_version:
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
    result: list[DatasetArtifact] = []
    for raw in raw_artifacts:
        if not isinstance(raw, Mapping):
            raise DatasetCatalogError("dataset manifest contains an invalid artifact")
        language = str(raw.get("language", ""))
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
    payload = _request_json(url)
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


def _remote_artifacts(
    *,
    language: str | None = None,
    version: str | None = None,
    variant: str | None = None,
) -> tuple[DatasetArtifact, ...]:
    releases = _releases(version)
    selected_variant = _variant(variant) if variant is not None else None
    if not releases:
        raise DatasetNotFound("no published compatible dataset release was found")
    errors: list[DatasetError] = []
    incompatible_schemas: set[str] = set()
    for release in releases:
        try:
            artifacts = _manifest_for_release(release)
        except DatasetError as exc:
            if version is not None:
                raise
            errors.append(exc)
            continue
        language_items = tuple(
            artifact
            for artifact in artifacts
            if (language is None or artifact.language == _language(language))
            and (selected_variant is None or artifact.variant == selected_variant)
        )
        selected = tuple(artifact for artifact in language_items if _remote_compatible(artifact))
        incompatible_schemas.update(
            artifact.schema_version
            for artifact in language_items
            if artifact.schema_version != SCHEMA_VERSION
        )
        if selected:
            return selected
        if version is not None:
            if language_items:
                schemas = ", ".join(sorted({item.schema_version for item in language_items}))
                raise DatasetIncompatible(
                    f"Dataset {_version_from_tag(_release_tag(version))} uses schema {schemas}; "
                    f"this Lexhint requires schema {SCHEMA_VERSION}."
                )
            raise DatasetNotFound(
                f"dataset release {_release_tag(version)!r} has no requested language"
            )
    if errors:
        raise errors[-1]
    if incompatible_schemas:
        newest = ", ".join(sorted(incompatible_schemas))
        requested = language or "the requested language"
        raise DatasetIncompatible(
            f"No compatible {requested} dataset found for Lexhint schema {SCHEMA_VERSION}. "
            f"Newest available artifacts use schema {newest}."
        )
    raise DatasetNotFound("no published release contains the requested language")


def available_datasets(
    *,
    language: str | None = None,
    version: str | None = None,
    variant: str | None = None,
    offline: bool = False,
) -> tuple[DatasetArtifact, ...]:
    if offline:
        raise DatasetCatalogError("dataset catalog access is unavailable in offline mode")
    return _remote_artifacts(language=language, version=version, variant=variant)


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
    return dataset


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
    return tuple(
        sorted(result, key=lambda item: (item.language, item.variant, item.dataset_version))
    )


def _release_key(dataset: InstalledDataset) -> tuple[str, str, str]:
    return (dataset.release_published_at, dataset.installed_at, dataset.dataset_version)


def resolve_installed_dataset(
    language: str,
    *,
    variant: str | None = None,
    version: str | None = None,
) -> InstalledDataset:
    normalized = _language(language)
    if variant is not None:
        variant = _variant(variant)
    candidates: list[InstalledDataset] = []
    all_candidates = list_installed_datasets(normalized)
    for candidate in all_candidates:
        if variant is not None and candidate.variant != variant:
            continue
        if version is not None and candidate.dataset_version != version:
            continue
        candidates.append(candidate)
    if not candidates:
        selector = f"/{variant}" if variant else ""
        if version:
            selector += f"/{version}"
        raise DatasetNotFound(f"no compatible installed dataset for {normalized}{selector}")
    if variant is not None or version is not None:
        return max(candidates, key=_release_key)
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


def _installed_for_artifact(
    artifact: DatasetArtifact, *, already_installed: bool
) -> InstalledDataset:
    path = _artifact_path(
        artifact.language, artifact.variant, artifact.dataset_version, artifact.schema_version
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
    )


def _write_sidecar(path: Path, artifact: DatasetArtifact, installed_at: str) -> None:
    payload = {
        "install_format": 1,
        "language": artifact.language,
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
    version: str | None = None,
    force: bool = False,
    offline: bool = False,
    progress: Callable[[DatasetProgress], None] | None = None,
) -> InstalledDataset:
    if offline:
        raise DatasetDownloadError("dataset downloads are unavailable in offline mode")
    normalized = _language(language)
    variant = _variant(variant)
    artifacts = _remote_artifacts(language=normalized, version=version, variant=variant)
    matching = list(artifacts)
    if not matching:
        raise DatasetNotFound(
            f"no published dataset for {normalized}/{variant}" + (f"/{version}" if version else "")
        )
    artifact = matching[0]
    if artifact.schema_version != SCHEMA_VERSION:
        raise DatasetIncompatible(
            f"Dataset {artifact.dataset_version} uses schema {artifact.schema_version}; "
            f"this Lexhint requires schema {SCHEMA_VERSION}."
        )
    _expected_capabilities(artifact)
    final_path = _artifact_path(
        artifact.language, artifact.variant, artifact.dataset_version, artifact.schema_version
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
        if metadata.get("schema_version") != artifact.schema_version:
            raise DatasetIntegrityError("dataset schema does not match the manifest")
        if metadata.get("coverage") != artifact.coverage:
            raise DatasetIntegrityError("dataset coverage does not match the manifest")
        if capabilities != artifact.capabilities:
            raise DatasetIntegrityError("dataset capabilities do not match the manifest")
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


def remove_dataset(language: str, *, variant: str, version: str | None = None) -> tuple[Path, ...]:
    normalized = _language(language)
    variant = _variant(variant)
    root = data_dir() / "datasets" / normalized / variant
    if version is not None:
        paths = [_artifact_path(normalized, variant, version, SCHEMA_VERSION)]
    else:
        schema_root = root / f"s{SCHEMA_VERSION}"
        paths = sorted(schema_root.glob("*/lexhint.sqlite3")) if schema_root.is_dir() else []
    removed: list[Path] = []
    for path in paths:
        if path.is_file():
            shutil.rmtree(path.parent)
            removed.append(path)
    if root.is_dir() and not any(root.iterdir()):
        root.rmdir()
    return tuple(removed)


def validate_datasets(
    language: str | None = None,
    *,
    variant: str | None = None,
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
            if version is not None and dataset.dataset_version != version:
                continue
            result.append(validate_installed_dataset(dataset))
    return tuple(result)


__all__ = [
    "DATASET_REPOSITORY",
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
    "InstalledDataset",
    "available_datasets",
    "download_dataset",
    "list_installed_datasets",
    "remove_dataset",
    "resolve_installed_dataset",
    "validate_datasets",
    "validate_installed_dataset",
    "supported_base_languages",
]
