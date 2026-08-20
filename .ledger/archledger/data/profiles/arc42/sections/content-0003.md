---
schema_version: 4
id: content-0003
kind: content
type: section
section: context_and_scope
title: Context and Scope
order: 30
status: accepted
version: 4
body_format: markdown
---

`lexhint` sits between lexical resources and a speech or text-normalization consumer.

## Business context

```text
FrequencyWords ──> common-word evidence ─┐
                                         ├─> lexhint ──> dictionary API ──> consumer
Wiktionary/Kaikki ─> rich entries ───────┘
                         └─> indexed topics ──> context evidence
```

The consumer decides how evidence affects pronunciation. For example, `lexhint` can report that `chat` is known and `gpt` is an unknown run, or that nearby `compiler` evidence supports a `computing` interpretation. It does not implement `Am -> A minor`, version pronunciation, URL symbol names, or other speech policy.

## Technical context

- Inputs are FrequencyWords text files and Wiktextract-compatible JSONL, either local or remote.
- The CLI and Python API read resources through the cache layer.
- The application process owns in-memory lexical data and read-only SQLite dictionary access.
- Lazy dictionary lookups request only exact Kaikki word pages and persist curated rich entries.
- Full builds stream the bulk JSONL source line by line into SQLite.
- Outputs are dataclasses, tuples, CLI text, or stable JSON. No service endpoint or daemon is required.
