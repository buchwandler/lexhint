from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import replace

from benchmarks.config import load_profile
from benchmarks.metrics import build_database
from benchmarks.model import SyntheticDataset
from benchmarks.report import render_report
from benchmarks.scaling import linear_fit, scaling_estimate
from benchmarks.schemas.compact_experiment import WithoutRowidSearchAdapter
from benchmarks.schemas.current_v8 import CurrentV8Adapter
from benchmarks.schemas.schema10_candidate import Schema10CandidateAdapter
from benchmarks.workloads import run_workloads
from lexhint.store import create_schema


def smoke_dataset() -> SyntheticDataset:
    return SyntheticDataset(load_profile("smoke"))


def schema_objects(connection: sqlite3.Connection) -> list[tuple[str, str, str, str]]:
    return [
        (row[0], row[1], row[2], " ".join((row[3] or "").split()))
        for row in connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master "
            "WHERE name NOT LIKE ? ORDER BY type, name",
            ("sqlite_%",),
        )
    ]


def test_same_seed_is_deterministic_and_unique() -> None:
    first = smoke_dataset()
    second = smoke_dataset()
    first_words = [row.word for row in first.iter_lexemes()]
    second_words = [row.word for row in second.iter_lexemes()]
    assert first_words == second_words
    assert len(first_words) == first.profile.lexemes
    assert len(set(first_words)) == first.profile.lexemes
    assert list(first.iter_entries()) == list(second.iter_entries())
    assert list(first.iter_senses()) == list(second.iter_senses())


def test_changed_seed_changes_generated_content() -> None:
    profile = load_profile("smoke")
    changed = SyntheticDataset(replace(profile, seed=profile.seed + 1))
    assert [row.word for row in smoke_dataset().iter_lexemes()] != [
        row.word for row in changed.iter_lexemes()
    ]


def test_schema10_candidate_has_production_storage_shape() -> None:
    with (
        closing(sqlite3.connect(":memory:")) as production,
        closing(sqlite3.connect(":memory:")) as benchmark,
    ):
        create_schema(production)
        Schema10CandidateAdapter().create(benchmark)
        production_sql = {name: sql for _, name, _, sql in schema_objects(production)}
        benchmark_sql = {name: sql for _, name, _, sql in schema_objects(benchmark)}
        assert "WITHOUT ROWID" in benchmark_sql["lexeme_ngrams"]
        assert "WITHOUT ROWID" in benchmark_sql["headword_relations"]
        assert "entries_display_word_idx" not in benchmark_sql
        assert "entries_word_idx" in production_sql


def test_build_is_valid_and_records_shape(tmp_path) -> None:
    metrics = build_database(
        CurrentV8Adapter(),
        smoke_dataset(),
        tmp_path / "database.sqlite3",
        batch_size=16,
        command="test",
    )
    assert metrics["format"] == "lexhint-sqlite-benchmark.v1"
    assert metrics["build"]["quick_check"] == "ok"
    assert metrics["counts"]["lexemes"] == 64
    assert metrics["counts"]["entries"] > metrics["counts"]["lexemes"]
    assert metrics["size"]["as_built"]["raw_bytes"] > 0
    assert metrics["size"]["as_built"]["gzip_bytes"] > 0
    assert metrics["size"]["as_built"]["page_count"] > 0
    assert "sqlite_version" in metrics["sqlite"]
    assert render_report(metrics).startswith("# Lexhint SQLite Benchmark")


def open_built(path, adapter=None):
    adapter = adapter or CurrentV8Adapter()
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    adapter.create(connection)
    adapter.populate(connection, smoke_dataset(), batch_size=16)
    adapter.finalize(connection)
    return connection, adapter


def test_current_v8_workloads_return_expected_results(tmp_path) -> None:
    connection, adapter = open_built(tmp_path / "database.sqlite3")
    assert adapter.exact_lookup(connection, "compile") is not None
    assert adapter.exact_lookup(connection, "unknown-word") is None
    assert adapter.complete(connection, "comp", 10)[0] == "compile"
    assert "compile" in adapter.suggest(connection, "compil", 10)["candidates"]
    assert adapter.dictionary_lookup(connection, "compile")[0]["senses"]
    assert adapter.definition_search(connection, ("object",), match="any")
    assert adapter.definition_search(connection, ("object", "system"), match="all")
    connection.close()


def test_without_rowid_adapter_preserves_results(tmp_path) -> None:
    current_path = tmp_path / "current.sqlite3"
    compact_path = tmp_path / "compact.sqlite3"
    current = build_database(
        CurrentV8Adapter(), smoke_dataset(), current_path, batch_size=16, command="test"
    )
    compact = build_database(
        WithoutRowidSearchAdapter(), smoke_dataset(), compact_path, batch_size=16, command="test"
    )
    assert current["counts"] == compact["counts"]
    connection = sqlite3.connect(compact_path)
    for table in ("lexeme_ngrams", "sense_search_terms"):
        sql = connection.execute("SELECT sql FROM sqlite_master WHERE name=?", (table,)).fetchone()[
            0
        ]
        assert sql.rstrip().endswith("WITHOUT ROWID")
    connection.close()


def test_workload_metrics_have_percentiles_and_diagnostics(tmp_path) -> None:
    path = tmp_path / "database.sqlite3"
    build_database(CurrentV8Adapter(), smoke_dataset(), path, batch_size=16, command="test")
    results = run_workloads(
        CurrentV8Adapter(), path, smoke_dataset().query_corpus(), warmup=1, iterations=2
    )
    assert results["exact_lookup_hit_0"]["iterations"] == 2
    assert "median_us" in results["exact_lookup_hit_0"]
    assert "p95_us" in results["exact_lookup_hit_0"]
    assert results["suggest_distance_1_0"]["candidate_words"] >= 1
    assert results["definition_multi_all_0"]["result_count"] >= 1


def test_result_json_shape_can_be_serialized(tmp_path) -> None:
    metrics = build_database(
        CurrentV8Adapter(),
        smoke_dataset(),
        tmp_path / "database.sqlite3",
        batch_size=16,
        command="test",
    )
    json.dumps(metrics)
    required = {
        "format",
        "created_at",
        "schema",
        "profile",
        "environment",
        "sqlite",
        "counts",
        "build",
        "size",
        "objects",
        "workloads",
    }
    assert required <= metrics.keys()


def test_scaling_regression_and_held_out_prediction() -> None:
    assert linear_fit([(1, 10), (2, 20), (3, 30)])["r_squared"] == 1.0
    metrics = [
        {
            "profile": {"lexemes": x},
            "size": {"as_built": {"raw_bytes": 10 * x + 5, "gzip_bytes": 2 * x + 3}},
        }
        for x in (1, 2, 3, 4)
    ]
    estimate = scaling_estimate(metrics, 10)
    assert estimate["predicted_raw_bytes"] == 105
    assert estimate["predicted_gzip_bytes"] == 23
    assert estimate["held_out"]["raw_error_percent"] == 0
