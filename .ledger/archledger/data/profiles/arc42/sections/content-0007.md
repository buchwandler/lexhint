---
schema_version: 4
id: content-0007
kind: content
type: section
section: deployment_view
title: Deployment View
order: 70
status: accepted
version: 10
body_format: markdown
---

Lexhint is deployed as a local Python package and a local SQLite evidence artifact. There is no application server, worker, or persistent service.

- Consumers install the package and open an artifact with `Lexicon.from_path()` or the default `Lexicon` resolution.
- Artifact paths are selected by the caller or build workflow; CLI `--path` is an explicit override.
- `dictionary status` reports current row counts, schema, capabilities, source format, source contract, and provenance without rebuilding the artifact.
- A complete local artifact supports offline lexical, segmentation, dictionary, semantic, fuzzy, headword, relation, and definition-search reads when the corresponding capabilities are present.
- Generated artifacts contain source and hash provenance for dictionary and corpus inputs.
- Build downloads and replacements use temporary files and atomic rename.
- Generated external datasets are distributed separately from code according to `DATA_SOURCES.md`.
