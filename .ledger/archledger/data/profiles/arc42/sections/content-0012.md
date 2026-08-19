---
schema_version: 4
id: content-0012
kind: content
type: section
section: glossary
title: Glossary
order: 120
status: accepted
version: 2
body_format: markdown
---

- **Lexicon:** A frequency-ranked list used for common-word membership and identifier segmentation.
- **Segment:** An immutable result identifying a known lexical span or an unknown run, optionally with rank.
- **Dictionary sense:** A compact word entry containing display spelling, part of speech, glosses, and explicit topics.
- **Topic:** Semantic metadata supplied by Wiktextract/Kaikki and used as context evidence.
- **Context support:** A topic score and cue list showing that nearby non-target words support a requested interpretation.
- **Partial coverage:** A schema-v4 dictionary containing only explicitly looked-up word pages and their lookup statuses.
- **Full coverage:** A schema-v4 dictionary built from a complete compatible JSONL source. It is authoritative for local reads.
- **Target span:** The source character interval whose candidate interpretation is being evaluated. It is excluded from context evidence.
- **Kaikki:** The upstream publication used for exact-word and bulk Wiktextract-derived dictionary data.
- **FrequencyWords:** The upstream 50k frequency lists used to provide common-word ranks.
- **Spokenform:** The downstream speech/text-normalization layer that consumes lexhint evidence and owns pronunciation policy.
