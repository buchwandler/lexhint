---
schema_version: 4
id: content-0009
kind: content
type: section
section: architecture_decisions
title: Architecture Decisions
order: 90
status: accepted
version: 7
body_format: markdown
---

The current architecture records these decisions.

- **Use a self-describing SQLite artifact.** Schema, language, coverage, profile, capabilities, and provenance are validated at runtime.
- **Separate lexical, semantic, and dictionary capabilities.** Consumers can select the evidence they need without allowing data from an older artifact to leak into a fresh build.
- **Treat frequency as enrichment.** Corpus rank improves segmentation and commonness evidence but does not define lexical capability.
- **Build fresh artifacts atomically.** Capability-specific tables are created from the resolved build plan and replacements cannot expose partial output.
- **Use stable semantic domains.** Raw source topics are projected into a small deterministic taxonomy at build time.
- **Exclude the candidate from context evidence.** A target token cannot validate its own interpretation.
- **Keep the runtime read-only and offline by default.** Acquisition belongs to explicit build workflows.
- **Keep a narrow consumer boundary.** Lexhint supplies evidence; downstream consumers own interpretation and speech rendering.
