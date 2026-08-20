---
schema_version: 4
id: content-0011
kind: content
type: section
section: risks_and_technical_debt
title: Risks and Technical Debt
order: 110
status: accepted
version: 4
body_format: markdown
---

- **Upstream availability and format drift.** FrequencyWords and Kaikki are external services. URL, JSONL, or source-shape changes can prevent acquisition. Validation and controlled download errors reduce silent corruption, but source compatibility still needs monitoring.
- **External data licensing.** Generated dictionary indexes inherit obligations from Wiktionary, Wiktextract, Kaikki, and source corpora. Redistribution must follow `DATA_SOURCES.md`; the architecture intentionally does not hide this risk.
- **Heuristic segmentation.** Dynamic-programming scores and the two-letter guard are practical heuristics, not linguistic analysis. New languages or identifier styles may require tuning and more representative evaluation data.
- **Incomplete local coverage.** Lazy caches only know requested words, and no external network is available in offline mode. Consumers must handle absent evidence rather than treating it as a negative semantic result.
- **Schema evolution.** SQLite metadata and migration behavior are versioned, but full indexes may require explicit rebuilds after incompatible changes.
- **Limited production telemetry.** The library reports local results and build statistics but does not collect usage or upstream health metrics. Operational monitoring belongs to the embedding application.
- **Scope boundary.** `lexhint` does not pronounce text, resolve all language morphology, or perform general word-sense disambiguation. Those capabilities remain downstream or future work.
