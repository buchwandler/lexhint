"""Standard-library scaling fits and aggregate SQLite calibration."""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import replace
from pathlib import Path
from statistics import median
from typing import Any

from .model import SyntheticProfile


def linear_fit(points: list[tuple[float, float]]) -> dict[str, float | int]:
    if len(points) < 2:
        raise ValueError("at least two points are required for a scaling fit")
    x_mean = sum(x for x, _ in points) / len(points)
    y_mean = sum(y for _, y in points) / len(points)
    denominator = sum((x - x_mean) ** 2 for x, _ in points)
    slope = (
        sum((x - x_mean) * (y - y_mean) for x, y in points) / denominator if denominator else 0.0
    )
    intercept = y_mean - slope * x_mean
    predicted = [intercept + slope * x for x, _ in points]
    total = sum((y - y_mean) ** 2 for _, y in points)
    residual = sum((y - estimate) ** 2 for (_, y), estimate in zip(points, predicted, strict=True))
    return {
        "points": len(points),
        "slope": slope,
        "intercept": intercept,
        "r_squared": 1.0 - residual / total if total else 1.0,
        "residual_stddev": math.sqrt(residual / max(1, len(points) - 2)),
    }


def scaling_estimate(metrics: list[dict[str, Any]], target_lexemes: int) -> dict[str, Any]:
    if len(metrics) < 2:
        raise ValueError("a scale estimate requires at least two measured runs")
    raw_points = [
        (float(item["profile"]["lexemes"]), float(item["size"]["as_built"]["raw_bytes"]))
        for item in metrics
    ]
    gzip_points = [
        (float(item["profile"]["lexemes"]), float(item["size"]["as_built"]["gzip_bytes"]))
        for item in metrics
    ]
    raw_fit = linear_fit(raw_points)
    gzip_fit = linear_fit(gzip_points)
    held_out: dict[str, Any] | None = None
    if len(metrics) >= 3:
        training_raw = linear_fit(raw_points[:-1])
        training_gzip = linear_fit(gzip_points[:-1])
        actual_raw = raw_points[-1][1]
        actual_gzip = gzip_points[-1][1]
        raw_prediction = training_raw["intercept"] + training_raw["slope"] * raw_points[-1][0]
        gzip_prediction = training_gzip["intercept"] + training_gzip["slope"] * gzip_points[-1][0]
        held_out = {
            "lexemes": int(raw_points[-1][0]),
            "raw_actual": actual_raw,
            "raw_predicted": raw_prediction,
            "raw_error_percent": (raw_prediction - actual_raw) / actual_raw * 100
            if actual_raw
            else 0.0,
            "gzip_actual": actual_gzip,
            "gzip_predicted": gzip_prediction,
            "gzip_error_percent": (gzip_prediction - actual_gzip) / actual_gzip * 100
            if actual_gzip
            else 0.0,
        }
    return {
        "measured_lexemes": [int(x) for x, _ in raw_points],
        "target_lexemes": target_lexemes,
        "raw_fit": raw_fit,
        "gzip_fit": gzip_fit,
        "predicted_raw_bytes": raw_fit["intercept"] + raw_fit["slope"] * target_lexemes,
        "predicted_gzip_bytes": gzip_fit["intercept"] + gzip_fit["slope"] * target_lexemes,
        "raw_range": [
            max(
                0.0,
                raw_fit["intercept"]
                + raw_fit["slope"] * target_lexemes
                - 2 * raw_fit["residual_stddev"],
            ),
            raw_fit["intercept"]
            + raw_fit["slope"] * target_lexemes
            + 2 * raw_fit["residual_stddev"],
        ],
        "gzip_range": [
            max(
                0.0,
                gzip_fit["intercept"]
                + gzip_fit["slope"] * target_lexemes
                - 2 * gzip_fit["residual_stddev"],
            ),
            gzip_fit["intercept"]
            + gzip_fit["slope"] * target_lexemes
            + 2 * gzip_fit["residual_stddev"],
        ],
        "held_out": held_out,
        "caution": (
            "Synthetic text and B-tree behavior are assumptions; extrapolation beyond "
            "the largest measured scale can introduce error."
        ),
    }


def calibrate_profile(path: str | Path, *, name: str = "english-measured") -> SyntheticProfile:
    database = Path(path)
    connection = sqlite3.connect(database)
    try:

        def count(table: str) -> int:
            row = connection.execute("SELECT COUNT(*) FROM " + table).fetchone()
            return int(row[0]) if row else 0

        lexemes = count("lexemes")
        entries = count("entries") if _has_table(connection, "entries") else 0
        senses = count("senses") if _has_table(connection, "senses") else 0
        semantic_rows = count("lexeme_domains") if _has_table(connection, "lexeme_domains") else 0
        ngrams = count("lexeme_ngrams") if _has_table(connection, "lexeme_ngrams") else 0
        search_terms = (
            count("sense_search_terms") if _has_table(connection, "sense_search_terms") else 0
        )
        lengths = [row[0] for row in connection.execute("SELECT length(word) FROM lexemes")]
        median_length = median(lengths) if lengths else 8.0
        averages: dict[str, float] = {}
        for column in ("etymology", "forms", "pronunciations"):
            if _has_table(connection, "entries"):
                averages[column] = float(
                    connection.execute(
                        f"SELECT COALESCE(AVG(length({column})), 0) FROM entries"
                    ).fetchone()[0]
                )
        for column in ("glosses", "topics", "tags", "examples", "synonyms", "antonyms"):
            if _has_table(connection, "senses"):
                averages[column] = float(
                    connection.execute(
                        f"SELECT COALESCE(AVG(length({column})), 0) FROM senses"
                    ).fetchone()[0]
                )
        base = SyntheticProfile(
            name=name,
            seed=20260823,
            lexemes=max(1, lexemes),
            entries_per_lexeme_mean=entries / lexemes if lexemes else 1.0,
            senses_per_entry_mean=senses / entries if entries else 1.0,
            headword_length_mean=statistics_mean(lengths),
            headword_length_stddev=statistics_stddev(lengths),
            etymology_length_mean=int(averages.get("etymology", 0)),
            gloss_length_mean=int(averages.get("glosses", 48)),
            semantic_coverage=semantic_rows / lexemes if lexemes else 0.0,
            domains_per_semantic_lexeme_mean=semantic_rows / max(1, semantic_rows),
            assumption_note=(
                f"Calibrated from aggregate statistics in {database}; "
                f"ngrams={ngrams}, search_terms={search_terms}, "
                f"median_headword_length={median_length}."
            ),
        )
        return replace(base)
    finally:
        connection.close()


def _has_table(connection: sqlite3.Connection, table: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        is not None
    )


def statistics_mean(values: list[int]) -> float:
    return sum(values) / len(values) if values else 8.0


def statistics_stddev(values: list[int]) -> float:
    if len(values) < 2:
        return 0.0
    mean = statistics_mean(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def load_metrics(path: str | Path) -> list[dict[str, Any]]:
    candidate = Path(path)
    paths = sorted(candidate.glob("*/metrics.json")) if candidate.is_dir() else [candidate]
    values = []
    for item in paths:
        with item.open(encoding="utf-8") as handle:
            value = json.load(handle)
        if isinstance(value, dict):
            values.append(value)
    return values
