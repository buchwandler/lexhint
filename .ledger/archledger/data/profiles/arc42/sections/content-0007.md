---
schema_version: 4
id: content-0007
kind: content
type: section
section: deployment_view
title: Deployment View
order: 70
status: accepted
version: 3
body_format: markdown
---

`lexhint` is deployed as a local Python package and command-line executable. There is no application server, worker, or persistent service.

- The package is installed from a wheel or source distribution and exposes the `lexhint` entry point.
- Vendored word lists or dictionaries, when deliberately included, are package data under `lexhint/data`.
- Otherwise, word lists live under the user cache at `words/<language>.txt.gz` with a provenance sidecar at `words/<language>.metadata.json`, and dictionaries at `dictionaries/<language>.sqlite3`.
- FrequencyWords downloads use a pinned upstream revision and validate the normalized cache against its sidecar.
- Lazy dictionary downloads use exact Kaikki word-page URLs.
- Bulk dictionary builds may read the official Kaikki raw JSONL URL or a local compatible file.
- `--offline` prevents missing dictionary data from being fetched. A complete local index supports fully offline context queries.
- Temporary files are created beside cache targets and atomically renamed into place, limiting partially written resources.
- Code-only release artifacts do not include user caches or generated external datasets.
