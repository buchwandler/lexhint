---
schema_version: 4
id: content-0012
kind: content
type: section
section: glossary
title: Glossary
order: 120
status: accepted
version: 7
body_format: markdown
---

- **Lexicon:** The read-only runtime that opens one self-describing SQLite evidence artifact.
- **Lexeme:** A dictionary-derived lexical row with case flags and optional corpus fields.
- **SemanticDomain:** A stable taxonomy value projected from supported source topics.
- **Capability:** An explicit artifact feature such as `lexical`, `semantic`, or `dictionary`.
- **Full coverage:** An authoritative artifact suitable for segmentation and semantic context queries.
- **Context cue:** A nearby non-target token whose domain evidence contributes a bounded score.
- **Target span:** The source character interval excluded from semantic context evidence.
- **Wiktextract/Kaikki:** The upstream dictionary data used for lexical, semantic, and rich dictionary builds.
- **FrequencyWords:** The upstream corpus source used to enrich existing lexemes with commonness fields.
- **Spokenform:** A downstream consumer that owns tokenization, interpretation, pronunciation, and speech policy.
