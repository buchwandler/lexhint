---
schema_version: 4
id: content-0009
kind: content
type: section
section: architecture_decisions
title: Architecture Decisions
order: 90
status: accepted
version: 14
body_format: markdown
---
The current architecture records these decisions.

- **Use a self-describing SQLite artifact.** Schema, language, coverage, profile, capabilities, and provenance are validated at runtime.
- **Separate lexical, semantic, dictionary, and search capabilities.** Consumers can select evidence and index size intentionally without allowing data from an older artifact to leak into a fresh build.
- **Use deterministic sense identity and compact schema 10 artifacts.** Every retained sense receives a versioned Lexhint-owned ID based on stable identity fields and legitimate upstream provenance. Published artifacts use explicit schema 10 rebuilds, compact compound-key tables, and read-only finalization checks.
- **Use indexed lexical ranges for completion.** `complete()` is a local read-only normalized prefix query with exact-match priority and explicit frequency or lexical ordering.
- **Treat frequency as enrichment.** Corpus rank improves segmentation and commonness evidence but does not define lexical capability.
- **Build fresh artifacts atomically.** Capability-specific tables are created from the resolved build plan and replacements cannot expose partial output.
- **Use stable semantic domains.** Raw source topics are projected into a small deterministic taxonomy at build time.
- **Expose case attestation without weakening segmentation.** `word()` exposes normalized membership and stored case forms, while `segment()` retains surface-case acceptance so consumers can apply context-specific policy.
- **Anchor semantic context to character spans.** Overlapping target tokens are excluded; a target with no lexical token is a virtual boundary whose adjacent cues remain eligible at distance 1.
- **Treat semantic context as soft evidence.** Lexhint reports explainable hints, not sense disambiguation or semantic certainty.
- **Keep the runtime read-only and offline by default.** Acquisition belongs to explicit build workflows.
- **Keep a narrow consumer boundary.** Lexhint supplies evidence; downstream consumers own interpretation and speech rendering.
- **Do not mirror the full Wiktextract schema or adopt online provider plugins, runtime caches, raw Wiktionary parsing, translations, or audio persistence.**

- **Keep sense_topics compact.** Option B stores `(topic, sense_id)` without redundant entry IDs or unused indexes.
- **Separate dictionary content from search indexes.** The named `dictionary` profile preserves dictionary fidelity without the larger search structures.
