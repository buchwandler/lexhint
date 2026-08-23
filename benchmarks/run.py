#!/usr/bin/env python3
"""Command-line entry point for the local Lexhint SQLite benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from benchmarks.config import immutable_run_directory, load_profile, write_config
from benchmarks.metrics import build_database, write_json
from benchmarks.model import SyntheticDataset, SyntheticProfile
from benchmarks.report import render_report
from benchmarks.scaling import calibrate_profile, load_metrics, scaling_estimate
from benchmarks.schemas import get_adapter
from benchmarks.workloads import run_workloads

DEFAULT_RESULTS = Path(__file__).resolve().parent / "results"


def _profile(args: argparse.Namespace) -> SyntheticProfile:
    return load_profile(args.profile)


def _capabilities(args: argparse.Namespace) -> tuple[str, ...] | None:
    values = getattr(args, "capability", None)
    return tuple(values) if values else None


def _write_result(directory: Path, metrics: dict[str, Any], queries: dict[str, list[str]]) -> None:
    write_json(directory / "metrics.json", metrics)
    write_json(directory / "queries.json", queries)
    (directory / "report.md").write_text(render_report(metrics), encoding="utf-8")


def _build_in(
    directory: Path, schema: str, profile: SyntheticProfile, args: argparse.Namespace
) -> dict[str, Any]:
    dataset = SyntheticDataset(profile)
    adapter = get_adapter(schema, capabilities=_capabilities(args))
    database = directory / "database.sqlite3"
    metrics = build_database(
        adapter,
        dataset,
        database,
        batch_size=args.batch_size,
        command=" ".join(sys.argv),
        vacuum=args.vacuum,
    )
    metrics["config"] = {
        "connection_mode": args.connection_mode,
        "warmup": args.warmup,
        "iterations": args.iterations,
    }
    return metrics


def _new_directory(args: argparse.Namespace, schema: str, profile: SyntheticProfile) -> Path:
    return immutable_run_directory(args.results_dir, schema, profile)


def command_build(args: argparse.Namespace) -> None:
    profile = _profile(args)
    directory = _new_directory(args, args.schema, profile)
    metrics = _build_in(directory, args.schema, profile, args)
    queries = SyntheticDataset(profile).query_corpus()
    write_config(
        directory / "config.json",
        {
            "command": "build",
            "schema": args.schema,
            "profile": asdict(profile),
            "directory": str(directory),
        },
    )
    _write_result(directory, metrics, queries)
    print(directory)


def command_query(args: argparse.Namespace) -> None:
    directory = Path(args.input)
    queries_path = directory / "queries.json"
    queries = json.loads(queries_path.read_text(encoding="utf-8"))
    adapter = get_adapter(args.schema, capabilities=_capabilities(args))
    workloads = run_workloads(
        adapter,
        directory / "database.sqlite3",
        queries,
        warmup=args.warmup,
        iterations=args.iterations,
        connection_mode=args.connection_mode,
    )
    metrics = json.loads((directory / "metrics.json").read_text(encoding="utf-8"))
    metrics["workloads"] = workloads
    _write_result(directory, metrics, queries)
    print(directory)


def command_all(args: argparse.Namespace) -> None:
    profile = _profile(args)
    directory = _new_directory(args, args.schema, profile)
    metrics = _build_in(directory, args.schema, profile, args)
    queries = SyntheticDataset(profile).query_corpus()
    metrics["workloads"] = run_workloads(
        get_adapter(args.schema, capabilities=_capabilities(args)),
        directory / "database.sqlite3",
        queries,
        warmup=args.warmup,
        iterations=args.iterations,
        connection_mode=args.connection_mode,
    )
    write_config(
        directory / "config.json",
        {
            "command": "all",
            "schema": args.schema,
            "profile": asdict(profile),
            "directory": str(directory),
        },
    )
    _write_result(directory, metrics, queries)
    print(directory)


def _comparison_report(comparison: dict[str, Any]) -> str:
    lines = [
        "# Lexhint SQLite Benchmark Comparison",
        "",
        "| Metric | " + " | ".join(comparison["schemas"]) + " |",
        "|---|" + "---:|" * len(comparison["schemas"]),
    ]
    for metric in (
        "raw_bytes",
        "gzip_bytes",
        "delta_raw_bytes",
        "delta_gzip_bytes",
        "exact_lookup_hit_0_median_us",
        "completion_broad_0_limit_20_median_us",
        "suggest_distance_1_0_median_us",
        "definition_common_0_median_us",
    ):
        values = [comparison["results"][schema].get(metric) for schema in comparison["schemas"]]
        lines.append(
            f"| {metric} | "
            + " | ".join(
                "—"
                if value is None
                else f"{value:.2f}"
                if isinstance(value, float)
                else f"{value:,}"
                for value in values
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "- Results are directly comparable only when adapters claim equivalent semantics.",
            "- Timing values are machine-dependent baselines, not pass/fail thresholds.",
        ]
    )
    return "\n".join(lines) + "\n"


def _run_comparison(args: argparse.Namespace, capabilities: tuple[str, ...] | None = None) -> None:
    profile = _profile(args)
    root = _new_directory(args, "comparison", profile)
    summary: dict[str, Any] = {"schemas": args.schema, "results": {}}
    for schema in args.schema:
        child = root / schema
        child.mkdir()
        child_args = argparse.Namespace(**vars(args))
        child_args.capability = list(capabilities or getattr(args, "capability", []) or [])
        metrics = _build_in(child, schema, profile, child_args)
        queries = SyntheticDataset(profile).query_corpus()
        metrics["workloads"] = run_workloads(
            get_adapter(schema, capabilities=capabilities),
            child / "database.sqlite3",
            queries,
            warmup=args.warmup,
            iterations=args.iterations,
            connection_mode=args.connection_mode,
        )
        _write_result(child, metrics, queries)
        workload = metrics["workloads"]
        size = metrics["size"]["as_built"]
        summary["results"][schema] = {
            "raw_bytes": size["raw_bytes"],
            "gzip_bytes": size["gzip_bytes"],
        }
        for key in (
            "exact_lookup_hit_0",
            "completion_broad_0_limit_20",
            "suggest_distance_1_0",
            "definition_common_0",
        ):
            if key in workload:
                summary["results"][schema][f"{key}_median_us"] = workload[key]["median_us"]
    write_json(root / "comparison.json", summary)
    (root / "report.md").write_text(_comparison_report(summary), encoding="utf-8")
    print(root)


def command_compare(args: argparse.Namespace) -> None:
    if len(args.schema) < 2:
        raise ValueError("compare requires at least two --schema values")
    _run_comparison(args)


def command_compare_capabilities(args: argparse.Namespace) -> None:
    variants = tuple(args.variants.split(","))
    profile = _profile(args)
    root = _new_directory(args, "capabilities", profile)
    summary: dict[str, Any] = {"variants": variants, "results": {}}
    for variant in variants:
        child = root / variant
        child.mkdir()
        child_args = argparse.Namespace(**vars(args))
        child_args.capability = [variant]
        metrics = _build_in(child, args.schema, profile, child_args)
        queries = SyntheticDataset(profile).query_corpus()
        metrics["workloads"] = run_workloads(
            get_adapter(args.schema, capabilities=(variant,)),
            child / "database.sqlite3",
            queries,
            warmup=args.warmup,
            iterations=args.iterations,
            connection_mode=args.connection_mode,
        )
        _write_result(child, metrics, queries)
        summary["results"][variant] = metrics["size"]["as_built"]
    baseline = summary["results"].get("lexical")
    if baseline is not None:
        for value in summary["results"].values():
            value["delta_raw_bytes"] = value["raw_bytes"] - baseline["raw_bytes"]
            value["delta_gzip_bytes"] = value["gzip_bytes"] - baseline["gzip_bytes"]
    write_json(root / "comparison.json", summary)
    (root / "report.md").write_text(
        _comparison_report(
            {
                "schemas": list(variants),
                "results": {key: value for key, value in summary["results"].items()},
            }
        ),
        encoding="utf-8",
    )
    print(root)


def command_scale(args: argparse.Namespace) -> None:
    base = _profile(args)
    scales = [int(value) for value in args.scales.split(",") if value.strip()]
    root = _new_directory(args, f"scale-{args.schema}", base)
    metrics_list = []
    for scale in scales:
        profile = replace(base, lexemes=scale, name=f"{base.name}-{scale}")
        child = root / f"{scale:06d}"
        child.mkdir()
        metrics = _build_in(child, args.schema, profile, args)
        _write_result(child, metrics, SyntheticDataset(profile).query_corpus())
        metrics_list.append(metrics)
    estimate = scaling_estimate(metrics_list, args.target_lexemes or base.lexemes)
    write_json(root / "estimate.json", estimate)
    (root / "report.md").write_text(
        "# Lexhint SQLite Scaling Estimate\n\n"
        + json.dumps(estimate, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    print(root)


def command_estimate(args: argparse.Namespace) -> None:
    profile = load_profile(args.target_profile or args.profile)
    metrics = load_metrics(args.input)
    estimate = scaling_estimate(metrics, args.target_lexemes or profile.lexemes)
    root = _new_directory(args, "estimate", profile)
    write_json(root / "estimate.json", estimate)
    (root / "report.md").write_text(
        "# English estimate\n\n" + json.dumps(estimate, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(root)


def command_calibrate(args: argparse.Namespace) -> None:
    profile = calibrate_profile(args.path, name=args.name)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(asdict(profile), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(output)


def _common(parser: argparse.ArgumentParser, *, include_schema: bool = True) -> None:
    if include_schema:
        parser.add_argument("--schema", default="current-v8")
    parser.add_argument("--profile", default="smoke")
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--capability", action="append")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--connection-mode", choices=("persistent", "reopen"), default="persistent")
    parser.add_argument("--vacuum", action="store_true")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Lexhint synthetic SQLite schema benchmark")
    commands = root.add_subparsers(dest="command", required=True)
    for name, function in (("build", command_build), ("all", command_all)):
        command = commands.add_parser(name)
        _common(command)
        command.set_defaults(function=function)
    query = commands.add_parser("query")
    _common(query)
    query.add_argument("--input", type=Path, required=True)
    query.set_defaults(function=command_query)
    compare = commands.add_parser("compare")
    _common(compare, include_schema=False)
    compare.add_argument("--schema", action="append", required=True)
    compare.set_defaults(function=command_compare)
    capabilities = commands.add_parser("compare-capabilities")
    _common(capabilities)
    capabilities.add_argument("--variants", default="lexical,runtime,dictionary,rich")
    capabilities.set_defaults(function=command_compare_capabilities)
    scale = commands.add_parser("scale")
    _common(scale)
    scale.add_argument("--scales", required=True)
    scale.add_argument("--target-lexemes", type=int)
    scale.set_defaults(function=command_scale)
    estimate = commands.add_parser("estimate")
    _common(estimate)
    estimate.add_argument("--input", type=Path, required=True)
    estimate.add_argument("--target-profile")
    estimate.add_argument("--target-lexemes", type=int)
    estimate.set_defaults(function=command_estimate)
    calibrate = commands.add_parser("calibrate")
    calibrate.add_argument("--path", type=Path, required=True)
    calibrate.add_argument("--output", type=Path, required=True)
    calibrate.add_argument("--name", default="english-measured")
    calibrate.set_defaults(function=command_calibrate)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    args.function(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
