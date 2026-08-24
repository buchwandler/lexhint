"""Lexhint-shaped workload generation and repeatable timing summaries."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from statistics import median
from typing import Any

from .schema_api import SchemaAdapter


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, set):
        return sorted(_jsonable(item) for item in value)
    return value


def result_signature(value: Any) -> str:
    payload = json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _percentile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * percentile))))
    return ordered[index]


def summarize_durations(durations_ns: list[int]) -> dict[str, int | float]:
    if not durations_ns:
        return {"iterations": 0, "median_us": 0.0, "p95_us": 0.0, "p99_us": 0.0}
    return {
        "iterations": len(durations_ns),
        "median_us": median(durations_ns) / 1_000,
        "p95_us": _percentile(durations_ns, 0.95) / 1_000,
        "p99_us": _percentile(durations_ns, 0.99) / 1_000,
        "min_us": min(durations_ns) / 1_000,
        "max_us": max(durations_ns) / 1_000,
    }


def _connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def _run_case(
    name: str,
    invoke: Callable[[sqlite3.Connection], Any],
    connection: sqlite3.Connection,
    *,
    database_path: Path,
    warmup: int,
    iterations: int,
    connection_mode: str,
) -> dict[str, Any]:
    if connection_mode not in {"persistent", "reopen"}:
        raise ValueError("connection_mode must be persistent or reopen")
    for _ in range(warmup):
        if connection_mode == "reopen":
            warm_connection = _connection(database_path)
            try:
                invoke(warm_connection)
            finally:
                warm_connection.close()
        else:
            invoke(connection)
    durations: list[int] = []
    first_result: Any = None
    for _ in range(iterations):
        measured_connection = connection
        owned = False
        if connection_mode == "reopen":
            measured_connection = _connection(database_path)
            owned = True
        start = time.perf_counter_ns()
        result = invoke(measured_connection)
        durations.append(time.perf_counter_ns() - start)
        if first_result is None:
            first_result = result
        if owned:
            measured_connection.close()
    record: dict[str, Any] = {"name": name, "connection_mode": connection_mode}
    record.update(summarize_durations(durations))
    record["result_signature"] = result_signature(first_result)
    if isinstance(first_result, Mapping):
        for key in (
            "candidate_rows",
            "candidate_words",
            "surviving_words",
            "gram_count",
            "index_rows",
        ):
            if key in first_result:
                record[key] = first_result[key]
        if "candidates" in first_result:
            record["result_count"] = len(first_result["candidates"])
    elif isinstance(first_result, (list, tuple)):
        record["result_count"] = len(first_result)
    elif first_result is None:
        record["result_count"] = 0
    else:
        record["result_count"] = 1
    return record


def run_workloads(
    adapter: SchemaAdapter,
    database_path: str | Path,
    queries: dict[str, list[str]],
    *,
    warmup: int = 20,
    iterations: int = 200,
    connection_mode: str = "persistent",
) -> dict[str, dict[str, Any]]:
    """Run shared query inputs against an adapter and return stable metric records."""

    path = Path(database_path)
    connection = _connection(path)
    records: dict[str, dict[str, Any]] = {}
    try:

        def add(name: str, fn: Callable[[sqlite3.Connection], Any]) -> None:
            records[name] = _run_case(
                name,
                fn,
                connection,
                database_path=path,
                warmup=warmup,
                iterations=iterations,
                connection_mode=connection_mode,
            )

        for label, group in (("hit", "exact_hits"), ("miss", "exact_misses")):
            for index, word in enumerate(queries.get(group, [])):
                add(
                    f"exact_lookup_{label}_{index}",
                    lambda c, word=word: adapter.exact_lookup(c, word),
                )
        prefixes = (
            ("narrow", "prefix_narrow"),
            ("medium", "prefix_medium"),
            ("broad", "prefix_broad"),
            ("none", "prefix_no_match"),
        )
        for prefix_label, group in prefixes:
            for index, prefix in enumerate(queries.get(group, [])):
                for limit in (10, 20, 100):
                    add(
                        f"completion_{prefix_label}_{index}_limit_{limit}",
                        lambda c, prefix=prefix, limit=limit: adapter.complete(c, prefix, limit),
                    )
        for label, group in (
            ("simple", "dictionary_words_simple"),
            ("dense", "dictionary_words_dense"),
        ):
            for index, word in enumerate(queries.get(group, [])):
                add(
                    f"dictionary_{label}_{index}",
                    lambda c, word=word: adapter.dictionary_lookup(c, word),
                )
        for label, group in (
            ("distance_1", "suggest_distance_1"),
            ("distance_2", "suggest_distance_2"),
        ):
            for index, query in enumerate(queries.get(group, [])):
                add(
                    f"suggest_{label}_{index}", lambda c, query=query: adapter.suggest(c, query, 20)
                )
        definition_cases = (
            ("rare", "definition_rare", "any"),
            ("common", "definition_common", "any"),
            ("multi_all", "definition_multi_all", "all"),
            ("multi_any", "definition_multi_any", "any"),
        )
        for label, group, match in definition_cases:
            for index, term in enumerate(queries.get(group, [])):
                terms = tuple(queries[group]) if group.startswith("definition_multi") else (term,)
                add(
                    f"definition_{label}_{index}",
                    lambda c, terms=terms, match=match: adapter.definition_search(
                        c, terms, match=match, limit=20
                    ),
                )
        relation_lookup = getattr(adapter, "relation_lookup", None)
        reverse_relation_lookup = getattr(adapter, "reverse_relation_lookup", None)
        resolve_headword = getattr(adapter, "resolve_headword", None)
        if callable(relation_lookup):
            for index, word in enumerate(queries.get("relation_sources", [])):
                add(
                    f"relation_source_{index}",
                    lambda c, word=word: relation_lookup(c, word, 20),
                )
        if callable(reverse_relation_lookup):
            for index, word in enumerate(queries.get("relation_targets", [])):
                add(
                    f"relation_target_{index}",
                    lambda c, word=word: reverse_relation_lookup(c, word, 20),
                )
        if callable(resolve_headword):
            for index, word in enumerate(queries.get("relation_resolve", [])):
                add(
                    f"relation_resolve_{index}",
                    lambda c, word=word: resolve_headword(
                        c, word, ("redirect", "alternative", "form_of"), 20
                    ),
                )
        return records
    finally:
        connection.close()
