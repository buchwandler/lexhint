---
schema_version: 4
id: content-0012
kind: content
type: section
section: glossary
title: Glossary
order: 120
status: accepted
version: 6
body_format: markdown
---
- **Lexeme:** A canonical dictionary headword row with case flags and optional corpus count/rank.
- **LexicalSegment:** An immutable result identifying a compact-label span, with `known` evidence and an optional frequency rank. It does not decide pronunciation.
- **Dictionary entry:** An ordered headword/POS record containing optional forms, pronunciations, etymology, and grouped senses.
- **Dictionary sense:** A curated sense containing glosses, topics, usage tags, examples, and basic relations.
- **Topic:** Semantic metadata supplied by Wiktextract/Kaikki and used as context evidence.
- **Context cue:** A nearby source token with span, distance, and decay weight contributing to a topic score.
- **Topic evidence:** Soft diagnostic topic score and structured cue list showing that nearby non-target words support a requested interpretation. No evidence is not negative evidence.
- **Partial coverage:** A live schema-6 dictionary containing only explicitly looked-up word pages; it supports exact lookup but not reliable segmentation.
- **Full coverage:** A schema-6 dictionary built from a complete compatible JSONL source and suitable for segmentation. It is authoritative for local reads; local source builds record a reproducible snapshot hash.
- **Target span:** The source character interval whose candidate interpretation is being evaluated. It is excluded from context evidence.
- **Kaikki:** The upstream publication used for exact-word and bulk Wiktextract-derived dictionary data.
- **FrequencyWords:** The upstream 50k frequency lists used to provide common-word ranks.
- **Spokenform:** The downstream speech/text-normalization layer that consumes lexhint evidence and owns pronunciation policy.
