---
schema_version: 4
id: content-0010
kind: content
type: section
section: quality_requirements
title: Quality Requirements
order: 100
status: accepted
version: 5
body_format: markdown
---

| Quality attribute | Architectural response                                                                                                 | Observable scenario                                                                     |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| Correctness       | NFC and case-folded keys, display-aware dictionary selection, explicit language filtering, and target exclusion        | A candidate token is never used as its own context cue; unrelated context fails closed. |
| Determinism       | Stable source ordering, one-based ranks, bounded scoring parameters, immutable result models, and explicit JSON fields | Repeating a local query returns the same rank, segments, senses, and topic ordering.    |
| Performance       | Lazy resource loading, indexed SQLite word lookup, bounded context windows, and streaming bulk builds                  | A context query fetches only nearby missing non-target tokens.                          |
| Portability       | Python 3.10+, standard-library runtime, local files, and configurable cache roots                                      | The package runs without a service or third-party runtime installation.                 |
| Resilience        | Atomic resource replacement, cached empty lookups, offline mode, and controlled exceptions                             | A transient or unavailable network does not corrupt an existing cache.                  |
| Maintainability   | Focused modules, compact public models, documented data provenance, and boundary tests                                 | Storage, network parsing, segmentation, and CLI behavior can be tested independently.   |
| Compliance        | External resources remain separate from code and their licenses are documented                                         | A distributor can review data obligations before vendoring generated indexes.           |
