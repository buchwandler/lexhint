---
schema_version: 4
id: content-0008
kind: content
type: section
section: cross_cutting_concepts
title: Cross-cutting Concepts
order: 80
status: accepted
version: 11
body_format: markdown
---

### Capability-specific schema

Schema metadata is explicit and self-describing. `language`, `locale`, `variant`, `schema_version`, and `dataset_version` remain separate dimensions. Locale is optional and does not create `en-GB` or `en-US` artifacts. Strict equality, not a compatibility range, controls SQLite access.

Schema 7 metadata is explicit and self-describing. `lexemes` is always present for lexical capability and already stores lowercase, titlecase, and uppercase attestation flags exposed by `WordEvidence`. `lexeme_domains` exists only for `semantic`; each row stores bounded deterministic weight and source-topic provenance. Rich `entries`, `senses`, `sense_topics`, forms, and pronunciations exist only for `dictionary`. Old partial-cache schemas are rejected and must be rebuilt.

### Provenance and data lifecycle

Metadata records `dictionary_source`, `dictionary_source_sha256`, `frequency_source`, and `frequency_source_sha256`, alongside profile, capabilities, creation time, and builder version. Remote dictionary input is hashed while streamed. Automatic FrequencyWords sources are cached by pinned revision and language, validated against an atomic SHA-256 sidecar, and downloaded through temporary files followed by atomic rename.

### Errors and offline behavior

Capability, coverage, schema, language, and missing-artifact failures have controlled public exceptions. Offline mode rejects every HTTP(S) build source and permits only local or already validated cached inputs. Frequency acquisition fails the build unless the caller explicitly selects `--no-frequency` or a custom source. Missing semantic evidence is not semantic negation.

### Verification and licensing

Tests cover read-only behavior, no-network guards, segmentation, case attestation, virtual-boundary semantic target anchoring, schema and capability validation, frequency policy, semantic target exclusion, CLI contracts, and source extraction. External dictionary and corpus data remain subject to the obligations documented in `DATA_SOURCES.md`.
