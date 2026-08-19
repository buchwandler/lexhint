---
schema_version: 4
id: content-0009
kind: content
type: section
section: architecture_decisions
title: Architecture Decisions
order: 90
status: accepted
version: 2
body_format: markdown
---

The current architecture records these decisions.

- **Separate lexical and semantic resources.** Frequency rank answers common-word questions; dictionary senses answer semantic-context questions. Combining them would discard useful technical vocabulary.
- **Use compact SQLite rather than hand-maintained context JSON.** SQLite supports incremental word caching, indexed lookup, metadata validation, and complete offline indexes without mirroring raw Wiktionary data.
- **Use lazy fetch by default in the Python API.** Normal local reads do not unexpectedly access the network. Explicit CLI operations or `fetch_missing=True` opt into acquisition.
- **Exclude the candidate from its own context evidence.** This prevents a target token from falsely validating an interpretation based on its own dictionary topics.
- **Stream bulk sources.** Kaikki data is too large to require a temporary in-memory or duplicate raw copy; the builder processes it line by line.
- **Keep runtime dependencies to the standard library.** `urllib`, `sqlite3`, gzip, and dataclasses provide the required portability for a small library.
- **Use a narrow consumer boundary.** Speech pronunciation rules stay in the downstream speech layer instead of being duplicated in lexical infrastructure.
