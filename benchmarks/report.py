"""Compact Markdown rendering for benchmark result JSON."""

from __future__ import annotations

from typing import Any


def _size(value: Any) -> str:
    if value is None:
        return "—"
    return f"{int(value):,}"


def render_report(metrics: dict[str, Any]) -> str:
    schema = metrics.get("schema", {})
    profile = metrics.get("profile", {})
    size = metrics.get("size", {}).get("as_built", {})
    counts = metrics.get("counts", {})
    lines = [
        "# Lexhint SQLite Benchmark",
        "",
        "## Configuration",
        "",
        f"- Schema: `{schema.get('name', 'unknown')}` (source schema "
        f"{schema.get('source_schema_version', '?')})",
        f"- Profile: `{profile.get('name', 'unknown')}`; seed `{profile.get('seed', '?')}`",
        f"- Profile SHA-256: `{profile.get('sha256', 'unknown')}`",
        "",
        "## Dataset shape",
        "",
        "| Rows | Count |",
        "|---|---:|",
    ]
    for key in (
        "lexemes",
        "entries",
        "senses",
        "lexeme_ngrams",
        "sense_search_terms",
        "semantic_rows",
        "relations",
    ):
        lines.append(f"| {key} | {_size(counts.get(key))} |")
    lines.extend(
        [
            "",
            "## Database size",
            "",
            f"- Raw SQLite: **{_size(size.get('raw_bytes'))} bytes**",
            f"- Gzip: **{_size(size.get('gzip_bytes'))} bytes** "
            f"(ratio {size.get('compression_ratio', 0):.3f})",
            f"- Allocated / used estimate: {_size(size.get('allocated_bytes'))} / "
            f"{_size(size.get('used_estimate'))} bytes",
            "",
            "## Table/index size",
            "",
            "| Object | Bytes |",
            "|---|---:|",
        ]
    )
    for name, value in (metrics.get("objects") or {}).items():
        lines.append(f"| `{name}` | {_size(value)} |")
    relation_metrics = metrics.get("relations", {})
    if relation_metrics.get("rows") is not None:
        lines.extend(
            [
                "",
                "## Relation storage",
                "",
                f"- Rows: **{_size(relation_metrics.get('rows'))}**",
                f"- Indexed object bytes: **{_size(relation_metrics.get('object_bytes'))}**",
                f"- Bytes per relation: **{relation_metrics.get('bytes_per_relation', 0):.2f}**",
            ]
        )
    lines.extend(["", "## Build performance", ""])
    for name, phase in metrics.get("build", {}).get("phases", {}).items():
        lines.append(f"- `{name}`: {phase.get('seconds', 0):.4f}s; {_size(phase.get('rows'))} rows")
    lines.extend(
        [
            "",
            "## Lookup and search performance",
            "",
            "| Workload | Median µs | P95 µs | Results |",
            "|---|---:|---:|---:|",
        ]
    )
    for name, value in metrics.get("workloads", {}).items():
        lines.append(
            f"| `{name}` | {value.get('median_us', 0):.2f} | "
            f"{value.get('p95_us', 0):.2f} | {_size(value.get('result_count'))} |"
        )
    lines.extend(
        [
            "",
            "## Notes / unsupported features",
            "",
            "- `reopen` means closing and reopening SQLite; it does not flush the "
            "operating-system page cache.",
            "- Synthetic English profiles are explicit assumptions, not validated "
            "English measurements.",
            "- `dbstat` object sizes are reported when the SQLite build provides the "
            "virtual table.",
        ]
    )
    return "\n".join(lines) + "\n"
