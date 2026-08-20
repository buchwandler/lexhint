from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import lexhint.sources as sources
from lexhint import builder
from lexhint.builder import build_dictionary
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


FIXTURE = Path(__file__).parent / "fixtures" / "kaikki-mini.jsonl"


def test_custom_http_frequency_source_is_removed_after_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    downloaded: list[Path] = []

    def fake_download(_url: str, target: Path, *, timeout: float) -> None:
        downloaded.append(target)
        target.write_text("compiler 10\n", encoding="utf-8")

    monkeypatch.setattr(sources, "_download", fake_download)
    output = tmp_path / "en.sqlite3"
    build_dictionary(
        "en",
        FIXTURE,
        output=output,
        frequency_source="https://example.test/en_full.txt",
    )
    assert output.is_file()
    assert downloaded and not downloaded[0].exists()


def test_custom_http_frequency_source_is_removed_after_failed_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    downloaded: list[Path] = []

    def fake_download(_url: str, target: Path, *, timeout: float) -> None:
        downloaded.append(target)
        target.write_text("compiler 10\n", encoding="utf-8")

    def fail_entries(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("dictionary source failed")

    monkeypatch.setattr(sources, "_download", fake_download)
    monkeypatch.setattr(builder, "iter_wiktextract_entries", fail_entries)
    with pytest.raises(RuntimeError, match="dictionary source failed"):
        build_dictionary(
            "en",
            FIXTURE,
            output=tmp_path / "en.sqlite3",
            frequency_source="https://example.test/en_full.txt",
        )
    assert downloaded and not downloaded[0].exists()
