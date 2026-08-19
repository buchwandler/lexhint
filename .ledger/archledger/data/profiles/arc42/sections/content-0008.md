---
schema_version: 4
id: content-0008
kind: content
type: section
section: cross_cutting_concepts
title: Cross-cutting Concepts
order: 80
status: accepted
version: 2
body_format: markdown
---

### Normalization and identity

Unicode NFC normalization is used for stored display values and case folding for lookup keys. Dictionary rows retain display spelling so case-sensitive variants can be preferred without changing lookup identity.

### Data lifecycle and caching

Word lists are immutable normalized gzip files. Partial dictionaries maintain lookup status and timestamps so empty and not-found results are not repeatedly requested. Full coverage is authoritative and does not trigger lazy fetches. Schema compatibility is checked at runtime; partial schema-v3 caches are invalidated, while full incompatible indexes require a rebuild.

### Errors and offline behavior

Resource absence, malformed input, network failures, not-found results, incompatible metadata, and offline misses have distinct controlled exceptions. The CLI turns them into concise messages or JSON errors with actionable hints.

### Interfaces and observability

Python APIs return immutable dataclasses and tuples. CLI JSON serializes explicit fields and build statistics. Progress reporting is sent to stderr and is used only for interactive bulk builds.

### Verification and licensing

Tests cover segmentation, parsing, schema behavior, lazy fetching, target exclusion, and CLI contracts using fixtures and mocked network access. External data provenance and redistribution duties are maintained separately in `DATA_SOURCES.md`.
