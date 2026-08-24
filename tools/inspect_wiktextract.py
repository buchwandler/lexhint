#!/usr/bin/env python3
"""Inspect one word in a local Wiktextract/Kaikki JSONL source."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlparse

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lexhint.builder import iter_wiktextract_entries
from lexhint.extract import dictionary_entries, relation_candidates
from lexhint.languages import normalize_language
from lexhint.models import ExtractionDiagnostics
from lexhint.store import normalize_display_word
from lexhint.wiktextract_types import RETAINED_ENTRY_FIELDS, RETAINED_SENSE_FIELDS


def _local_source(path: Path) -> Path:
    if urlparse(str(path)).scheme in {"http", "https"}:
        raise ValueError("source inspection accepts local JSONL or JSONL.gz paths only")
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def inspect_source(path: Path, *, language: str, word: str) -> dict[str, object]:
    target = normalize_display_word(word)
    records: list[dict[str, object]] = []
    diagnostics = ExtractionDiagnostics()
    for raw in iter_wiktextract_entries(_local_source(path), offline=True):
        if normalize_display_word(str(raw.get("word") or "")) != target:
            continue
        entries = tuple(dictionary_entries(raw, language=language, diagnostics=diagnostics))
        relations = relation_candidates(raw, language=language)
        entry_fields = set(raw)
        retained = entry_fields & set(RETAINED_ENTRY_FIELDS)
        dropped = entry_fields - retained
        sense_fields = {
            field
            for sense in raw.get("senses", ())
            if isinstance(sense, dict)
            for field in set(sense) & set(RETAINED_SENSE_FIELDS)
        }
        records.append(
            {
                "source_fields": sorted(entry_fields),
                "retained_fields": sorted(retained | sense_fields),
                "dropped_fields": sorted(dropped),
                "entries": [asdict(entry) for entry in entries],
                "relations": [asdict(relation) for relation in relations],
            }
        )
    return {
        "source": str(path),
        "language": normalize_language(language),
        "word": target,
        "records": records,
        "entries": [entry for record in records for entry in record["entries"]],
        "relations": [relation for record in records for relation in record["relations"]],
        "diagnostics": diagnostics.as_dict(),
    }


def _text_report(result: dict[str, object]) -> str:
    lines = [f"{result['word']} ({result['language']})", f"records: {len(result['records'])}"]
    for index, record in enumerate(result["records"], start=1):
        lines.extend(
            [
                f"record {index}",
                "  source fields: " + ", ".join(record["source_fields"]),
                "  retained: " + ", ".join(record["retained_fields"]),
                (
                    "  dropped: " + ", ".join(record["dropped_fields"])
                    if record["dropped_fields"]
                    else "  dropped: none"
                ),
                f"  entries: {len(record['entries'])}",
                f"  relations: {len(record['relations'])}",
            ]
        )
    lines.append("diagnostics: " + json.dumps(result["diagnostics"], sort_keys=True))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--language", required=True)
    parser.add_argument("--word", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = inspect_source(args.source, language=args.language, word=args.word)
    output = (
        json.dumps(result, ensure_ascii=False, sort_keys=True)
        if args.json
        else _text_report(result)
    )
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
