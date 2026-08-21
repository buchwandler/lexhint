from __future__ import annotations

import hashlib
import os
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .download import cache_dir, user_agent
from .frequency import FREQUENCYWORDS_REVISION
from .languages import normalize_language


@dataclass(frozen=True, slots=True)
class ResolvedFrequencySource:
    path: Path
    provider: str
    corpus: str
    revision: str
    source_url: str
    sha256: str
    temporary: bool = False


def _sidecar_path(path: Path) -> Path:
    return path.with_name(path.name + ".sha256")


def _write_sidecar(path: Path, digest: str) -> None:
    sidecar = _sidecar_path(path)
    fd, temporary = tempfile.mkstemp(prefix=f".{sidecar.name}.", dir=sidecar.parent)
    os.close(fd)
    temporary_path = Path(temporary)
    try:
        temporary_path.write_text(digest + "\n", encoding="ascii")
        temporary_path.replace(sidecar)
    finally:
        temporary_path.unlink(missing_ok=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cache_path(language: str, revision: str) -> Path:
    return cache_dir() / "sources" / "frequencywords" / revision / f"{language}_full.txt"


def _download(url: str, target: Path, *, timeout: float) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    os.close(fd)
    temporary_path = Path(temporary)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": user_agent()})
        with (
            urllib.request.urlopen(request, timeout=timeout) as response,
            temporary_path.open("wb") as handle,
        ):
            while chunk := response.read(1024 * 1024):
                handle.write(chunk)
        if temporary_path.stat().st_size == 0:
            raise OSError("downloaded source is empty")
        temporary_path.replace(target)
    finally:
        temporary_path.unlink(missing_ok=True)


def resolve_frequency_source(
    language: str,
    *,
    source: str | Path | None = None,
    enabled: bool = True,
    refresh: bool = False,
    offline: bool = False,
    timeout: float = 60.0,
) -> ResolvedFrequencySource | None:
    if not enabled:
        return None
    base_language = normalize_language(language)
    if source is not None:
        source_value = str(source)
        parsed = urlparse(source_value)
        if parsed.scheme in {"http", "https"}:
            if offline:
                raise OSError("HTTP frequency sources are unavailable in offline mode")
            fd, temporary = tempfile.mkstemp(prefix="lexhint-frequency-")
            os.close(fd)
            local = Path(temporary)
            try:
                _download(source_value, local, timeout=timeout)
                digest = _sha256(local)
                return ResolvedFrequencySource(
                    local, "custom", "custom", "custom", source_value, digest, True
                )
            except Exception:
                local.unlink(missing_ok=True)
                raise
        local = Path(source_value).expanduser()
        if not local.is_file():
            raise OSError(f"frequency source does not exist: {local}")
        return ResolvedFrequencySource(
            local, "custom", "custom", "custom", str(local), _sha256(local)
        )

    url = (
        "https://raw.githubusercontent.com/hermitdave/FrequencyWords/"
        f"{FREQUENCYWORDS_REVISION}/content/2018/{base_language}/{base_language}_full.txt"
    )
    target = _cache_path(base_language, FREQUENCYWORDS_REVISION)
    if refresh:
        target.unlink(missing_ok=True)
        _sidecar_path(target).unlink(missing_ok=True)
    if target.is_file():
        sidecar = _sidecar_path(target)
        expected = sidecar.read_text(encoding="ascii").strip() if sidecar.is_file() else ""
        digest = _sha256(target)
        if not expected or expected != digest:
            target.unlink()
            sidecar.unlink(missing_ok=True)
            if offline:
                raise OSError(
                    f"cached FrequencyWords source for {base_language} failed hash validation"
                )
    if not target.is_file():
        if offline:
            raise OSError(
                f"FrequencyWords full source is not cached for {base_language}; "
                "use --frequency-source or --no-frequency"
            )
        _download(url, target, timeout=timeout)
        _write_sidecar(target, _sha256(target))
    digest = _sha256(target)
    return ResolvedFrequencySource(
        target,
        "FrequencyWords",
        "OpenSubtitles2018",
        FREQUENCYWORDS_REVISION,
        url,
        digest,
    )
