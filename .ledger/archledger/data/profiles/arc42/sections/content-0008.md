---
schema_version: 4
id: content-0008
kind: content
type: section
section: cross_cutting_concepts
title: Cross-cutting Concepts
order: 80
status: accepted
version: 18
body_format: markdown
---
### Capability-specific schema

Schema metadata is explicit and self-describing. `language`, `locale`, `variant`, `schema_version`, and `dataset_version` remain separate dimensions. Locale is optional and does not create `en-GB` or `en-US` artifacts. Strict equality, not a compatibility range, controls SQLite access.

Schema 10 metadata is explicit and self-describing. `lexemes` is always present for lexical capability and stores lowercase, titlecase, and uppercase attestation flags exposed by `WordEvidence`. `lexeme_domains` exists only for `semantic`; rich `entries`, `senses`, `sense_topics`, and `headword_relations` exist only for `dictionary`; `lexeme_ngrams` exists for `search`; and `sense_search_terms` exists for `dictionary` plus `search`. Search and relation metadata record index and row counts, and projections remove claims for excluded structures. Schema 9 artifacts are rejected and must be rebuilt; schema 9 and schema 10 dataset families remain side by side on disk.

Managed dataset variants select capability subsets in a strict chain: `lexical`, `runtime` (`lexical,semantic`), `dictionary` (`lexical,semantic,dictionary`), and `rich` (`lexical,semantic,dictionary,search`). A dictionary projection supports full entry/sense/topic inspection, explicit relation lookup, rendering, semantic context, and completion while intentionally omitting fuzzy suggestion and indexed definition/reverse search. Only rich includes both search structures.

### Source contract and diagnostics

The build consumes a narrow Lexhint-owned TypedDict contract for the fields it intentionally retains: lexical identity, POS, senses, topics, forms, IPA sounds, etymology, examples, synonyms, antonyms, redirects, `alt_of`, and `form_of`. Translations, descendants, broader linkage taxonomies, audio URLs, IDs, raw glosses, categories, templates, and unknown fields are not persisted. Extraction diagnostics and the local inspection tool report retained and dropped fields without weakening defensive runtime checks.

### Provenance and data lifecycle

Metadata records `dictionary_source`, `dictionary_source_sha256`, `dictionary_source_format`, `dictionary_source_contract`, `frequency_source`, and `frequency_source_sha256`, alongside profile, capabilities, creation time, and builder version. Remote dictionary input is hashed while streamed. Automatic FrequencyWords sources are cached by pinned revision and language, validated against an atomic SHA-256 sidecar, and downloaded through temporary files followed by atomic rename.

### Relation decision evidence

The schema 10 benchmark compares a pre-schema-10 relation layout with compact compound-key tables and immutable index finalization. On the smoke profile, the candidate measured 204,800 raw bytes and 36,558 gzip bytes versus 425,984 raw bytes and 96,183 gzip bytes for the baseline. Suggestion and definition-search timings were slower in this two-iteration run, so the measurements are comparative evidence rather than English-dataset estimates.

### Errors and offline behavior

Capability, coverage, schema, language, and missing-artifact failures have controlled public exceptions. Offline mode rejects every HTTP(S) build source and permits only local or already validated cached inputs. Frequency acquisition fails the build unless the caller explicitly selects `--no-frequency` or a custom source. Missing semantic evidence is not semantic negation.

### Verification and licensing

Tests cover read-only behavior, no-network guards, segmentation, case attestation, virtual-boundary semantic target anchoring, schema and capability validation, frequency policy, semantic target exclusion, CLI contracts, source extraction, relation extraction/API/CLI/projection, and the managed four-variant resolver chain. External dictionary and corpus data remain subject to the obligations documented in `DATA_SOURCES.md`.


Raw bulk Wiktextract input does not contain Kaikki postprocessed website `sense.id` values. Lexhint therefore ignores that field, retains sparse `senseid` and Wikidata provenance when available, and generates a versioned deterministic `lh1-<language>-<encoded>` sense ID. High-cardinality translations and derived graphs remain optional data rather than core tables.
