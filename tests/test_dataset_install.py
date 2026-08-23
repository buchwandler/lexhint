from __future__ import annotations

import gzip
import hashlib
import io
from pathlib import Path

import pytest

import lexhint.datasets as datasets
from lexhint.builder import build_dictionary

FIXTURE = Path(__file__).parent / "fixtures" / "kaikki-mini.jsonl"


class Response(io.BytesIO):
    def __enter__(self) -> Response:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def test_streaming_install_verifies_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LEXHINT_DATA_DIR", str(tmp_path / "data"))
    source, _ = build_dictionary(
        "en", FIXTURE, output=tmp_path / "source.sqlite3", capabilities="lexical", no_frequency=True
    )
    database = source.read_bytes()
    compressed = gzip.compress(database)
    artifact = datasets.DatasetArtifact(
        "en",
        "lexical",
        "2026.08.20",
        "data-2026.08.20",
        "2026-08-21T00:00:00Z",
        2,
        "8",
        "custom",
        "full",
        ("lexical",),
        len(compressed),
        len(database),
        "lexhint-en-lexical-s8-2026.08.20.sqlite3.gz",
        hashlib.sha256(compressed).hexdigest(),
        "https://example.test/asset",
    )
    monkeypatch.setattr(datasets, "_remote_artifacts", lambda **kwargs: (artifact,))
    monkeypatch.setattr(datasets, "request", lambda *args, **kwargs: Response(compressed))

    installed = datasets.download_dataset("en", variant="lexical")
    assert installed.path.read_bytes() == database
    assert installed.path.with_name("artifact.json").is_file()
    assert not list(installed.path.parent.glob("*.gz"))
    assert datasets.download_dataset("en", variant="lexical").already_installed


def test_checksum_failure_does_not_install_final_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LEXHINT_DATA_DIR", str(tmp_path / "data"))
    compressed = gzip.compress(b"not a sqlite database")
    artifact = datasets.DatasetArtifact(
        "en",
        "lexical",
        "2026.08.20",
        "data-2026.08.20",
        "",
        2,
        "8",
        "custom",
        "full",
        ("lexical",),
        len(compressed),
        20,
        "asset",
        "0" * 64,
        "https://example.test/asset",
    )
    monkeypatch.setattr(datasets, "_remote_artifacts", lambda **kwargs: (artifact,))
    monkeypatch.setattr(datasets, "request", lambda *args, **kwargs: Response(compressed))
    with pytest.raises(datasets.DatasetIntegrityError):
        datasets.download_dataset("en", variant="lexical")
    assert not (
        tmp_path / "data" / "datasets" / "en" / "lexical" / "2026.08.20" / "lexhint.sqlite3"
    ).exists()
