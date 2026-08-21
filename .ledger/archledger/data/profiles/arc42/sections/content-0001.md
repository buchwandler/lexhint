---
schema_version: 4
id: content-0001
kind: content
type: section
section: introduction_and_goals
title: Introduction and Goals
order: 10
status: accepted
version: 9
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
- `word()` reports normalized lexical membership and the lowercase, titlecase, and uppercase forms attested by the artifact. `uppercase_only` is a convenience property for a known uppercase-only lexeme.
- `segment()` uses authoritative full coverage, case flags, dynamic programming, and optional corpus rank. It applies surface-case acceptance, so a case-folded word may be known to `word()` while its observed lowercase segment remains unknown.
- `entries()` requires the `dictionary` capability.
- `context_domains()` and `supports_domain()` require `semantic` and full coverage. Their target is a character span: overlapping lexical tokens are excluded, while a target containing no lexical token acts as a virtual boundary and keeps adjacent words eligible at distance 1.

Semantic context is soft evidence. Positive evidence is not semantic certainty, and missing evidence is not semantic negation. Capability, coverage, schema, language, and missing-artifact failures have controlled public exceptions.
