---
schema_version: 4
id: content-0002
kind: content
type: section
section: architecture_constraints
title: Architecture Constraints
order: 20
status: accepted
version: 11
body_format: markdown
---

The architecture is constrained by a local, self-describing SQLite artifact and by the external sources used to build it.

- `lexhint.Lexicon` opens artifacts through SQLite read-only mode.
- Runtime operations never fetch network resources, create missing lexemes, or write partial caches.
- The CLI resolves default cached or vendored artifacts for ordinary reads and exposes `dictionary status` for current SQL counts.
- `SCHEMA_VERSION` is an exact artifact compatibility key. Current schema 8 clients select and open only schema 8 artifacts; schema families are stored side by side under `s<schema>` paths.
- Metadata records schema version, base language, coverage, profile, capabilities, creation time, builder version, and source provenance.
- `lexemes` is present for the lexical capability. Semantic, dictionary, and search tables are capability-specific.
- Default builds select `lexical,semantic,dictionary,search` and automatic pinned full FrequencyWords enrichment.
- `search` provides indexed fuzzy headword and dictionary-text search; dictionary-text search requires both `dictionary` and `search`.
- Frequency is enrichment, not a capability.
- External dictionary and corpus data remain separate from the Apache-2.0 code and retain their licensing obligations.
