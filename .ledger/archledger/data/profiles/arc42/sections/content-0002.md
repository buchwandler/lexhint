---
schema_version: 4
id: content-0002
kind: content
type: section
section: architecture_constraints
title: Architecture Constraints
order: 20
status: accepted
version: 9
body_format: markdown
---

The architecture is constrained by a local, self-describing SQLite artifact and by the external sources used to build it.

- `lexhint.Lexicon` opens artifacts through SQLite read-only mode.
- Runtime operations never fetch network resources, create missing lexemes, or write partial caches.
- The CLI resolves default cached or vendored artifacts for ordinary reads and exposes `dictionary status` for current SQL counts.
- Schema 7 metadata records schema version, language, coverage, profile, capabilities, creation time, builder version, and source provenance.
- `lexemes` is present for the lexical capability. Semantic and dictionary tables are capability-specific.
- Default builds select `lexical,semantic,dictionary` and automatic pinned full FrequencyWords enrichment.
- Frequency is enrichment, not a capability.
- External dictionary and corpus data remain separate from the Apache-2.0 code and retain their licensing obligations.
