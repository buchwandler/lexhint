"""Profile and result-directory helpers."""

from __future__ import annotations

import json
import time
from pathlib import Path

from .model import SyntheticProfile

ROOT = Path(__file__).resolve().parent


def load_profile(name_or_path: str) -> SyntheticProfile:
    candidate = Path(name_or_path)
    if not candidate.exists():
        candidate = ROOT / "profiles" / f"{name_or_path}.json"
    return SyntheticProfile.from_json(candidate)


def immutable_run_directory(root: str | Path, schema: str, profile: SyntheticProfile) -> Path:
    base = Path(root)
    base.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    directory = base / f"{stamp}-{schema}-{profile.name}"
    suffix = 1
    while directory.exists():
        directory = base / f"{stamp}-{schema}-{profile.name}-{suffix}"
        suffix += 1
    directory.mkdir()
    return directory


def write_config(path: Path, values: dict[str, object]) -> None:
    path.write_text(json.dumps(values, indent=2, sort_keys=True) + "\n", encoding="utf-8")
