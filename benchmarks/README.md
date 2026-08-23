# Lexhint synthetic SQLite benchmark

This directory is a repository-local schema laboratory. It generates deterministic
synthetic dictionary data with the Python standard library, persists the same logical
data through multiple SQLite adapters, and records storage/build/query evidence.
It does not require Wiktextract, Kaikki, FrequencyWords, network access, or a released
dataset.

## Quick start

```bash
python benchmarks/run.py all --schema current-v8 --profile smoke
python benchmarks/run.py compare --schema current-v8 \
  --schema current-v8-without-rowid-search --profile smoke
python benchmarks/run.py scale --schema current-v8 --profile english-estimate \
  --scales 100,250,500,1000
```

Use `--results-dir /tmp/lexhint-bench` to keep generated files outside the checkout.
Each run creates an immutable timestamped directory with `config.json`,
`metrics.json`, `queries.json`, `report.md`, and disposable SQLite files.

## Design

`generate.py` produces a streamable logical dataset. Adapters in `schemas/` own
DDL, population, finalization, and workload queries. `current-v8` is a historical
snapshot of Lexhint schema 8; `current-v8-without-rowid-search` changes only the
compound search tables. Results include raw and gzip size, page metrics, optional
`dbstat` object attribution, build phases, and warm/reopen workload percentiles.

The English profile is an explicit synthetic assumption, not a measured English
fact. Use `calibrate` on aggregate statistics from a real artifact to create a
measured profile before relying on estimates.

## Profiles

- `smoke.json`: tiny correctness run;
- `small.json`: fast local iteration;
- `medium.json`: useful local comparison;
- `english_estimate.json`: target-shape assumptions for scale/estimate runs.

Benchmark timing is not a CI threshold. CI-style checks should use the smoke run
and logical correctness tests only.
