---
schema_version: 4
id: content-0011
kind: content
type: section
section: risks_and_technical_debt
title: Risks and Technical Debt
order: 110
status: accepted
version: 7
body_format: markdown
---

- **Upstream availability and format drift.** FrequencyWords and Wiktextract/Kaikki remain external inputs. Hash validation and source checks reduce silent corruption, but upstream changes can still prevent builds.
- **External data licensing.** Generated artifacts inherit obligations from their dictionary and corpus sources. Redistribution must follow `DATA_SOURCES.md`.
- **Heuristic segmentation.** Dynamic-programming segmentation is evidence, not linguistic analysis, and may need tuning for new languages or identifier styles.
- **Incomplete capability coverage.** A consumer cannot use dictionary or semantic operations when the artifact lacks those capabilities. Missing evidence must not be treated as semantic negation.
- **Schema evolution.** Incompatible schema or capability changes require rebuilding artifacts.
- **Scope boundary.** Lexhint does not pronounce text, tokenize all consumer inputs, or resolve interpretation precedence. Those responsibilities remain downstream.
