---
schema_version: 4
id: content-0002
kind: content
type: section
section: architecture_constraints
title: Architecture Constraints
order: 20
status: accepted
version: 15
body_format: markdown
---

The architecture is constrained by a local, self-describing SQLite artifact and by the external sources used to build it.

- `lexhint.Lexicon` opens artifacts through SQLite read-only mode.
- Runtime operations never fetch network resources, create missing lexemes, or write partial caches.
- The CLI resolves default cached or vendored artifacts for ordinary reads and exposes `dictionary status` for current SQL counts and source provenance.
- `SCHEMA_VERSION` is an exact artifact compatibility key. Schema 10 clients select and open only schema 10 artifacts; schema families are stored side by side under `s<schema>` paths and schema 9 artifacts must be rebuilt from source.
- Metadata records schema version, base language, coverage, profile, capabilities, creation time, builder version, dictionary source format and contract, and source provenance.
- `lexemes` is present for the lexical capability. Semantic, dictionary, search, and headword relation tables are capability-specific.
- Default builds select `lexical,semantic,dictionary,search` and automatic pinned full FrequencyWords enrichment.
- `search` provides indexed fuzzy headword and dictionary-text search; dictionary-text search requires both `dictionary` and `search`.
- Frequency is enrichment, not a capability.
- External dictionary and corpus data remain separate from the Apache-2.0 code and retain their licensing obligations.

Managed dataset variants are capability presets rather than exact mirrors of named build profiles: `runtime` provides `lexical,semantic` and remains the recommended default; `lexical` is the smallest projection; `dictionary` provides `lexical,semantic,dictionary` and includes explicit headword relations without search indexes; and `rich` provides `lexical,semantic,dictionary,search`. They form a strict capability chain so automatic installed-dataset resolution has one maximal result. The client tests this publisher contract so capability declarations cannot drift from schema construction.

Schema 10 finalization validates foreign keys and `PRAGMA quick_check`, runs `ANALYZE`, compacts the immutable artifact, and omits unused reverse indexes unless a protected workload justifies them. `sense_topics` uses Option B: a `(topic, sense_id)` `WITHOUT ROWID` table.
