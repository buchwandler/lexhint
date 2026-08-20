---
schema_version: 4
id: content-0003
kind: content
type: section
section: context_and_scope
title: Context and Scope
order: 30
status: accepted
version: 8
body_format: markdown
---

Lexhint sits between lexical data artifacts and a text-normalization or speech consumer.

## Business context

```text
Lexical and semantic evidence ──> lexhint ──> consumer interpretation and speech policy
Corpus frequency enrichment ────> lexhint ──> lexical ranking and evidence
```

The consumer decides what an unknown run, version, or candidate should mean. Lexhint ends at evidence and does not own tokenization, pronunciation, or interpretation precedence.

## Technical context

- Wiktextract/Kaikki JSONL supplies lexical and semantic data during builds.
- FrequencyWords enriches existing lexemes with corpus fields.
- A local SQLite artifact is the runtime boundary.
- No service endpoint or daemon is required.
