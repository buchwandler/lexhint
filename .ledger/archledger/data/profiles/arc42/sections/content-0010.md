---
schema_version: 4
id: content-0010
kind: content
type: section
section: quality_requirements
title: Quality Requirements
order: 100
status: accepted
version: 7
body_format: markdown
---

| Quality attribute | Architectural response                                                                                           | Observable scenario                                                                                |
| ----------------- | ---------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| Correctness       | Explicit schema and capability validation, case-aware lexemes, authoritative full coverage, and target exclusion | A candidate is never used as its own semantic cue and incompatible artifacts fail at construction. |
| Determinism       | Stable source projections, bounded weights, immutable build plans, and explicit result fields                    | Repeating a local query returns the same segments and evidence ordering.                           |
| Performance       | Indexed SQLite lookups, bounded context windows, batched nearby-word queries, and streamed builds                | A context query evaluates only the bounded local evidence window.                                  |
| Resilience        | Read-only runtime access, source hashes, temporary downloads, and atomic replacement                             | A failed build does not replace an existing artifact with partial output.                          |
| Maintainability   | Focused runtime and build modules, capability-specific schema, and boundary tests                                | Schema, extraction, semantic projection, storage, and CLI behavior can be checked independently.   |
| Compliance        | External resources remain separate from code and provenance is embedded in artifacts                             | A distributor can review data obligations before distributing generated artifacts.                 |
