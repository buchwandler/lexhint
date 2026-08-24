#!/usr/bin/env python3
"""Profile candidate headword relations in a local Wiktextract/Kaikki source."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lexhint.builder import iter_wiktextract_entries
from lexhint.extract import relation_candidates
from lexhint.languages import normalize_language
from lexhint.models import HeadwordRelation


def _local_source(path: Path) -> Path:
    if urlparse(str(path)).scheme in {"http", "https"}:
        raise ValueError("relation profiling accepts local JSONL or JSONL.gz paths only")
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * fraction)]


def _relation_bytes(relation: HeadwordRelation) -> int:
    return (
        sum(
            len(value.encode("utf-8"))
            for value in (
                relation.source,
                relation.target,
                relation.relation,
                "|".join(relation.tags),
            )
        )
        + 12
    )


def profile_source(path: Path, *, language: str) -> dict[str, object]:
    counts = Counter()
    headwords: set[str] = set()
    relations: set[HeadwordRelation] = set()
    per_headword: Counter[str] = Counter()
    tagged = 0
    estimated_bytes = 0
    for raw in iter_wiktextract_entries(_local_source(path), offline=True):
        counts["records_scanned"] += 1
        word = str(raw.get("word") or "")
        if word:
            headwords.add(word)
        for relation in relation_candidates(raw, language=language):
            relations.add(relation)
    for relation in sorted(relations, key=lambda item: (item.source, item.target, item.relation)):
        counts[relation.relation] += 1
        per_headword[relation.source] += 1
        tagged += int(bool(relation.tags))
        estimated_bytes += _relation_bytes(relation)
    cardinalities = list(per_headword.values())
    return {
        "source": str(path),
        "language": normalize_language(language),
        "records_scanned": counts["records_scanned"],
        "unique_headwords": len(headwords),
        "redirect_relationships": counts["redirect"],
        "alternative_relationships": counts["alternative"],
        "form_of_relationships": counts["form_of"],
        "unique_relation_rows": len(relations),
        "relations_per_headword": {
            "mean": len(relations) / len(headwords) if headwords else 0.0,
            "p50": _percentile(cardinalities, 0.50),
            "p95": _percentile(cardinalities, 0.95),
            "p99": _percentile(cardinalities, 0.99),
        },
        "tagged_relation_fraction": tagged / len(relations) if relations else 0.0,
        "estimated_normalized_text_bytes": estimated_bytes,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--language", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = profile_source(args.source, language=args.language)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    else:
        for key, value in result.items():
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
