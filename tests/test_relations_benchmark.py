from __future__ import annotations

import sqlite3

from benchmarks.config import load_profile
from benchmarks.metrics import build_database
from benchmarks.model import SyntheticDataset
from benchmarks.schemas.current_v8_relations import CurrentV8RelationsAdapter
from benchmarks.workloads import run_workloads


def test_relation_generation_is_deterministic() -> None:
    first = list(SyntheticDataset(load_profile("smoke")).iter_relations())
    second = list(SyntheticDataset(load_profile("smoke")).iter_relations())
    assert first == second
    assert first
    assert {relation.relation for relation in first} <= {"redirect", "alternative", "form_of"}


def test_relation_adapter_persists_and_queries_relations(tmp_path) -> None:
    dataset = SyntheticDataset(load_profile("smoke"))
    path = tmp_path / "relations.sqlite3"
    metrics = build_database(
        CurrentV8RelationsAdapter(), dataset, path, batch_size=16, command="test"
    )
    assert metrics["counts"]["relations"] > 0
    assert metrics["relations"]["bytes_per_relation"] > 0
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    adapter = CurrentV8RelationsAdapter()
    source = next(dataset.iter_relations()).source
    target = next(dataset.iter_relations()).target
    assert adapter.relation_lookup(connection, source)
    assert adapter.reverse_relation_lookup(connection, target)
    assert adapter.resolve_headword(connection, source)
    connection.close()


def test_relation_workloads_are_recorded(tmp_path) -> None:
    dataset = SyntheticDataset(load_profile("smoke"))
    path = tmp_path / "relations.sqlite3"
    build_database(CurrentV8RelationsAdapter(), dataset, path, batch_size=16, command="test")
    results = run_workloads(
        CurrentV8RelationsAdapter(),
        path,
        dataset.query_corpus(),
        warmup=1,
        iterations=2,
    )
    assert results["relation_source_0"]["iterations"] == 2
    assert results["relation_target_0"]["iterations"] == 2
    assert results["relation_resolve_0"]["iterations"] == 2
