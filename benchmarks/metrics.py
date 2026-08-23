"""Build, SQLite, environment, and artifact-size metrics."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import platform
import sqlite3
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .model import SyntheticDataset
from .schema_api import SchemaAdapter


def environment_metadata(command: str) -> dict[str, Any]:
    try:
        commit = (
            subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
            ).stdout.strip()
            or None
        )
    except OSError:
        commit = None
    return {
        "python_version": sys.version,
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "git_commit": commit,
        "command": command,
    }


def sqlite_settings(connection: sqlite3.Connection) -> dict[str, Any]:
    values: dict[str, Any] = {}
    version = connection.execute("SELECT sqlite_version()").fetchone()
    values["sqlite_version"] = version[0] if version else None
    for pragma in (
        "page_size",
        "journal_mode",
        "synchronous",
        "cache_size",
        "auto_vacuum",
        "foreign_keys",
    ):
        row = connection.execute(f"PRAGMA {pragma}").fetchone()
        values[pragma] = row[0] if row else None
    fts5 = connection.execute("SELECT sqlite_compileoption_used('ENABLE_FTS5')").fetchone()
    values["fts5_available"] = bool(fts5 and fts5[0])
    return values


def _gzip_file(path: Path, output: Path, level: int = 9) -> int:
    total = 0
    with (
        path.open("rb") as source,
        output.open("wb") as destination,
        gzip.GzipFile(fileobj=destination, mode="wb", compresslevel=level, mtime=0) as compressed,
    ):
        while chunk := source.read(1024 * 1024):
            compressed.write(chunk)
            total += len(chunk)
    return total


def object_sizes(connection: sqlite3.Connection) -> dict[str, int] | None:
    try:
        rows = connection.execute(
            "SELECT name, SUM(pgsize) FROM dbstat GROUP BY name ORDER BY SUM(pgsize) DESC"
        ).fetchall()
    except sqlite3.DatabaseError:
        return None
    return {str(row[0]): int(row[1]) for row in rows}


def measure_database(
    path: str | Path, *, gzip_path: str | Path | None = None, gzip_level: int = 9
) -> dict[str, Any]:
    database_path = Path(path)
    connection = sqlite3.connect(database_path)
    try:
        settings = {}
        for pragma in ("page_size", "page_count", "freelist_count"):
            settings[pragma] = int(connection.execute(f"PRAGMA {pragma}").fetchone()[0])
        allocated = settings["page_size"] * settings["page_count"]
        free = settings["page_size"] * settings["freelist_count"]
        result: dict[str, Any] = {
            "raw_bytes": database_path.stat().st_size,
            "allocated_bytes": allocated,
            "free_bytes": free,
            "used_estimate": allocated - free,
            **settings,
            "objects": object_sizes(connection),
        }
    finally:
        connection.close()
    compressed_path = (
        Path(gzip_path) if gzip_path else database_path.with_suffix(database_path.suffix + ".gz")
    )
    _gzip_file(database_path, compressed_path, gzip_level)
    result["gzip_bytes"] = compressed_path.stat().st_size
    result["gzip_level"] = gzip_level
    result["compression_ratio"] = (
        result["gzip_bytes"] / result["raw_bytes"] if result["raw_bytes"] else 0.0
    )
    result["gzip_path"] = str(compressed_path)
    return result


def quick_check(path: str | Path) -> str:
    connection = sqlite3.connect(path)
    try:
        return str(connection.execute("PRAGMA quick_check").fetchone()[0])
    finally:
        connection.close()


def build_database(
    adapter: SchemaAdapter,
    dataset: SyntheticDataset,
    path: str | Path,
    *,
    batch_size: int,
    command: str,
    vacuum: bool = False,
) -> dict[str, Any]:
    database_path = Path(path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    if database_path.exists():
        database_path.unlink()
    start = time.perf_counter_ns()
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    schema_start = time.perf_counter_ns()
    adapter.create(connection)
    schema_seconds = (time.perf_counter_ns() - schema_start) / 1_000_000_000
    build = adapter.populate(connection, dataset, batch_size=batch_size)
    adapter.finalize(connection)
    build.phases["schema_creation"] = {"seconds": schema_seconds, "rows": 0, "rows_per_second": 0.0}
    build.phases["total"] = {"seconds": (time.perf_counter_ns() - start) / 1_000_000_000}
    settings = sqlite_settings(connection)
    connection.close()
    as_built = measure_database(database_path)
    vacuumed = None
    if vacuum:
        vacuum_connection = sqlite3.connect(database_path)
        vacuum_connection.execute("VACUUM")
        vacuum_connection.close()
        vacuumed = measure_database(database_path)
    profile = dataset.profile
    return {
        "format": "lexhint-sqlite-benchmark.v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "schema": {
            "name": adapter.name,
            "source_schema_version": adapter.source_schema_version,
            "description": adapter.description,
        },
        "profile": {
            "name": profile.name,
            "seed": profile.seed,
            "sha256": profile.sha256(),
            **asdict(profile),
        },
        "environment": environment_metadata(command),
        "sqlite": settings,
        "counts": {**dataset.counts(), **build.counts},
        "build": {
            "phases": build.phases,
            "batch_size": batch_size,
            "quick_check": quick_check(database_path),
        },
        "size": {"as_built": as_built, "vacuumed": vacuumed},
        "objects": as_built.get("objects"),
        "workloads": {},
    }


def write_json(path: str | Path, value: object) -> None:
    with Path(path).open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
