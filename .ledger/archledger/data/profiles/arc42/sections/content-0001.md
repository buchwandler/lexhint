---
schema_version: 4
id: content-0001
kind: content
type: section
section: introduction_and_goals
title: Introduction and Goals
order: 10
status: accepted
version: 8
body_format: markdown
source_refs:
  - path: lexhint/lexicon.py
    role: documents
    reason: Lexicon runtime documented by the architecture
---

Lexhint is a small Python runtime plus prebuilt SQLite evidence artifacts. It supplies lexical membership, optional corpus commonness, compact-string segmentation, stable semantic-domain evidence, and optional rich dictionary inspection.

It does not decide how text is spoken. Spokenform and other consumers own tokenization policy, URLs, numbers, versions, acronyms, pronunciation, and interpretation precedence. Dataset publication is outside this repository.

## Runtime contract

- `word()` and `contains()` query dictionary-derived `lexemes`.
- `segment()` uses authoritative full coverage, case flags, dynamic programming, and optional corpus rank.
- `entries()` requires the `dictionary` capability.
- `context_domains()` and `supports_domain()` require `semantic` and full coverage.

Absence of semantic evidence is not semantic negation. Capability, coverage, schema, language, and missing-artifact failures have controlled public exceptions.
