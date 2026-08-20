from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import lexhint.sources as sources
from lexhint.sources import resolve_frequency_source


def test_automatic_frequency_cache_requires_matching_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sources, "cache_dir", lambda: tmp_path)
    target = (
        tmp_path / "sources" / "frequencywords" / sources.FREQUENCYWORDS_REVISION / "en_full.txt"
    )
    target.parent.mkdir(parents=True)
    target.write_text("compiler 10\n", encoding="utf-8")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    target.with_name(target.name + ".sha256").write_text(digest + "\n", encoding="ascii")

    resolved = resolve_frequency_source("en", offline=True)
    assert resolved is not None
    assert resolved.sha256 == digest

    target.write_text("corrupt 10\n", encoding="utf-8")
    with pytest.raises(OSError, match="hash validation"):
        resolve_frequency_source("en", offline=True)


def test_missing_automatic_frequency_source_is_controlled_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sources, "cache_dir", lambda: tmp_path)
    with pytest.raises(OSError, match="not cached"):
        resolve_frequency_source("en", offline=True)
