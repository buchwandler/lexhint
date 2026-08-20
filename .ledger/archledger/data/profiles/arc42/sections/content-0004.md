---
schema_version: 4
id: content-0004
kind: content
type: section
section: solution_strategy
title: Solution Strategy
order: 40
status: accepted
version: 6
body_format: markdown
---
The solution is organized around a small, explicit evidence pipeline.

## Strategy items

1. Keep dictionary membership and corpus frequency evidence evidence independent from semantic dictionary evidence. Technical dictionary cues must not be limited by a 50k frequency list.
2. Normalize Unicode to NFC and use case-folded lookup keys while retaining display spelling for dictionary results.
3. Query dictionary lexemes in bounded SQLite batches and use dynamic programming for compact-label segmentation. Unknown characters are merged into runs, and obscure two-letter matches are rejected to preserve initialisms. URL syntax remains the caller's responsibility.
4. Keep dictionary indexes curated. Store ordered entries and rich high-value lexical fields, while indexing topics separately for context scoring.
5. Make partial dictionary coverage incremental. Cache successful empty and not-found lookups and fetch only missing nearby context words when network access is explicitly allowed. Distinguish live partial caches from reproducible full snapshots.
6. Exclude the target span from topic scoring so a candidate cannot validate itself. Score nearby explicit topics with a bounded token window and distance decay.
7. Use a streaming bulk builder for complete offline coverage and atomic replacement of the resulting SQLite file.
8. Keep the integration boundary narrow. `spokenform` consumes evidence but remains responsible for interpretation and speech rendering.
