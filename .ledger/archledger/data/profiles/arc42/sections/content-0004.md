---
schema_version: 4
id: content-0004
kind: content
type: section
section: solution_strategy
title: Solution Strategy
order: 40
status: accepted
version: 7
body_format: markdown
---

The solution is organized around a small, explicit evidence pipeline.

1. Resolve canonical capabilities, profile, frequency mode, source paths, and offline or refresh policy in an immutable build plan before schema creation.
2. Keep lexical membership and corpus frequency evidence independent from semantic dictionary evidence.
3. Build rich dictionary tables only for the `dictionary` capability and materialize topic projections only for `semantic`.
4. Use authoritative full coverage, case flags, and dynamic programming for compact-string segmentation.
5. Exclude every token overlapping the target span from semantic context scoring.
6. Query nearby context words in batches and apply bounded distance decay to explicit domain evidence.
7. Validate pinned source hashes and use temporary files followed by atomic rename for downloaded and rebuilt artifacts.
8. Keep the consumer boundary narrow. Speech pronunciation rules remain downstream.
