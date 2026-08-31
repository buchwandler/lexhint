---
title: "Architecture Documentation"
version: 26
generator: "archledger 0.4.0"
arc42_template_version: "9.0-EN"
---

# Architecture Documentation

Generated from archledger records. Do not edit this generated file directly.

# Introduction and Goals

Lexhint is a small Python runtime plus prebuilt SQLite evidence artifacts. It supplies lexical membership, optional corpus commonness, compact-string segmentation, stable semantic-domain evidence, and optional rich dictionary inspection.

It does not decide how text is spoken. Spokenform and other consumers own tokenization policy, URLs, numbers, versions, acronyms, pronunciation, and interpretation precedence. Dataset publication is outside this repository.

## Runtime contract

- `word()` and `contains()` query dictionary-derived `lexemes`.
- `word()` reports normalized lexical membership and the lowercase, titlecase, and uppercase forms attested by the artifact. `uppercase_only` is a convenience property for a known uppercase-only lexeme.
- `segment()` uses authoritative full coverage, case flags, dynamic programming, and optional corpus rank. It applies surface-case acceptance, so a case-folded word may be known to `word()` while its observed lowercase segment remains unknown.
- `entries()` requires the `dictionary` capability.
- `context_domains()` and `supports_domain()` require `semantic` and full coverage. Their target is a character span: overlapping lexical tokens are excluded, while a target containing no lexical token acts as a virtual boundary and keeps adjacent words eligible at distance 1.

Semantic context is soft evidence. Positive evidence is not semantic certainty, and missing evidence is not semantic negation. Capability, coverage, schema, language, and missing-artifact failures have controlled public exceptions.

## Requirements Overview

<!-- archledger: no accepted records for this section yet -->

## Quality Goals

<!-- archledger: no accepted records for this section yet -->

## Stakeholders

<!-- archledger: no accepted records for this section yet -->

# Architecture Constraints

The architecture is constrained by a local, self-describing SQLite artifact and by the external sources used to build it.

- `lexhint.Lexicon` opens artifacts through SQLite read-only mode.
- Runtime operations never fetch network resources, create missing lexemes, or write partial caches.
- The CLI resolves default cached or vendored artifacts for ordinary reads and exposes `dictionary status` for current SQL counts and source provenance.
- `SCHEMA_VERSION` is an exact artifact compatibility key. Schema 10 clients select and open only schema 10 artifacts; schema families are stored side by side under `s<schema>` paths and schema 9 artifacts must be rebuilt from source.
- Metadata records schema version, base language, coverage, profile, capabilities, creation time, builder version, dictionary source format and contract, and source provenance.
- `lexemes` is present for the lexical capability. Semantic, dictionary, search, and headword relation tables are capability-specific.
- Default builds select `lexical,semantic,dictionary,search` and automatic pinned full FrequencyWords enrichment.
- `search` provides indexed fuzzy headword and dictionary-text search; dictionary-text search requires both `dictionary` and `search`.
- Frequency is enrichment, not a capability.
- External dictionary and corpus data remain separate from the Apache-2.0 code and retain their licensing obligations.

Managed dataset variants are capability presets rather than exact mirrors of named build profiles: `runtime` provides `lexical,semantic` and remains the recommended default; `lexical` is the smallest projection; `dictionary` provides `lexical,semantic,dictionary` and includes explicit headword relations without search indexes; and `rich` provides `lexical,semantic,dictionary,search`. They form a strict capability chain so automatic installed-dataset resolution has one maximal result. The client tests this publisher contract so capability declarations cannot drift from schema construction.

Schema 10 finalization validates foreign keys and `PRAGMA quick_check`, runs `ANALYZE`, compacts the immutable artifact, and omits unused reverse indexes unless a protected workload justifies them. `sense_topics` uses Option B: a `(topic, sense_id)` `WITHOUT ROWID` table.

## Schema 10 freeze and bump policy

Schema 10 is frozen at the `v0.4.0` release boundary. The structured contract in `lexhint.schema_contract` is the reviewable definition of the published SQLite layout. It covers required tables, ordered columns, primary and foreign keys, required indexes, `WITHOUT ROWID` tables, capability relationships, and persisted format versions. Runtime and managed dataset validation check that contract before capability-specific queries begin. SQLite `application_id` and `user_version` identify a Lexhint schema-10 file for diagnostics, while metadata `schema_version` remains authoritative.

A future change requires a schema bump unless it is proven compatible with existing schema-10 readers. Bump for required table or column additions, removals, or renames; primary-key or runtime-required foreign-key changes; required-index changes that alter query assumptions; incompatible JSON payload encodings; deterministic sense-ID type or anchor changes; or search-index construction changes that an existing reader would interpret differently. Schema 10 also covers the `lh1` public sense-ID interpretation, source provenance encoding, and the persisted forms, pronunciations, glosses, topics, tags, examples, synonyms, antonyms, relation tags, and semantic source-topic JSON arrays.

Optional metadata keys, diagnostics, error messages, rendering, additive runtime helpers, compatible performance work, and additional validation do not require a schema bump when stored and queried semantics remain unchanged. A schema bump requires rebuilding and republishing every managed variant. Schema 9 artifacts are never migrated in place.

<!-- archledger: no accepted records for this section yet -->

# Context and Scope

Lexhint sits between lexical data artifacts and a text-normalization or speech consumer.

## Business context

```text
Lexical and semantic evidence ──> lexhint ──> consumer interpretation and speech policy
Corpus frequency enrichment ────> lexhint ──> lexical ranking and evidence
```

The consumer decides what an unknown run, version, or candidate should mean. Lexhint ends at evidence and does not own tokenization, pronunciation, or interpretation precedence.

## Technical context

- Wiktextract/Kaikki JSONL supplies lexical and semantic data during builds.
- FrequencyWords enriches existing lexemes with corpus fields.
- A local SQLite artifact is the runtime boundary.
- No service endpoint or daemon is required.

## Business Context

<!-- archledger: no accepted records for this section yet -->

## Technical Context

<!-- archledger: no accepted records for this section yet -->

# Solution Strategy

The solution is organized around a small, explicit evidence pipeline.

1. Resolve canonical capabilities, profile, frequency mode, source paths, and offline or refresh policy in an immutable build plan before schema creation.
2. Keep lexical membership and corpus frequency evidence independent from semantic dictionary evidence.
3. Build rich dictionary tables only for the `dictionary` capability and materialize topic projections only for `semantic`.
4. Use authoritative full coverage, case flags, and dynamic programming for compact-string segmentation.
5. Exclude every token overlapping the target span from semantic context scoring.
6. Query nearby context words in batches and apply bounded distance decay to explicit domain evidence.
7. Validate pinned source hashes and use temporary files followed by atomic rename for downloaded and rebuilt artifacts.
8. Keep the consumer boundary narrow. Speech pronunciation rules remain downstream.
9. Emit build configuration and progress on stderr so successful JSON output remains a single stdout document.

## Strategy Items

<!-- archledger: no accepted records for this section yet -->

# Building Block View

The package is organized around a local artifact runtime and focused build modules.

- `lexhint.lexicon.Lexicon` owns read-only artifact access, lexical lookup, prefix completion, fuzzy suggestions, headword matching, indexed definition search, explicit headword relation lookup and resolution, segmentation, dictionary inspection, and semantic evidence queries.
- `lexhint.schema` defines schema and capability validation for the self-describing SQLite artifact.
- `lexhint.builder` creates fresh atomic artifacts from streamed source data and applies the immutable build plan.
- `lexhint.extract` converts source records into curated lexical and dictionary data plus explicit relation candidates.
- `lexhint.wiktextract_types` documents the narrow upstream JSONL contract consumed by Lexhint without depending on Wiktextract at runtime.
- `lexhint.semantics` projects source topics into the stable `SemanticDomain` taxonomy.
- `lexhint.frequency` and `lexhint.sources` resolve corpus enrichment and source provenance.
- `lexhint.store` persists lexemes, domains, rich dictionary tables, headword relations, search indexes, metadata, and indexes.
- `lexhint.cli` exposes build and runtime operations in human-readable and JSON forms.
- `tools/inspect_wiktextract.py` and `tools/profile_wiktextract_relations.py` are developer-only local source analysis tools.

The public package exports `Lexicon`, `HeadwordRelation`, `DictionarySearchHit`, and `SemanticDomain` as the principal consumer interface. It also exports `SCHEMA_VERSION`, `DATASET_VARIANTS`, `DATASET_VARIANT_NAMES`, `DEFAULT_DATASET_VARIANT`, and `supported_base_languages()` for the separate dataset publisher contract. Build and source helpers remain available from their owning modules.

## Consumer interface

```python
from lexhint import Lexicon, SemanticDomain

lexicon = Lexicon.from_path("en.sqlite3")
completions = lexicon.complete("comp")
suggestions = lexicon.suggest("complier")
headwords = lexicon.match_headwords("comp*", syntax="glob")
relations = lexicon.relations("colour")
targets = lexicon.resolve_headword("colours")
hits = lexicon.search_definitions("computer program", fields=("glosses",), match="all")
```

The consumer decides what an unknown run, version, or candidate should mean. Lexhint ends at evidence. Relation following is always explicit and does not alter `entries()` exact lookup.

<!-- archledger: no accepted records for this section yet -->

# Runtime View

## Lexical lookup and segmentation

1. The consumer constructs `Lexicon` from one local SQLite artifact, resolved from the vendored, configured cache, or schema-aware managed dataset path when no override is supplied.
2. Construction validates exact schema version, base language, coverage, and explicit capabilities before queries.
3. An optional locale such as `GB` or `US` is runtime presentation state. It does not change artifact resolution or physical English dataset identity. Regional source tags are defined once in `languages.py` and used by runtime ordering.
4. `word()` and `contains()` query lexical keys. `complete()` performs bounded normalized prefix completion through exact lookup and indexed lexical range queries; it is not fuzzy correction. `suggest()` uses bounded n-gram candidates, `match_headwords()` uses safe glob/regex scans, and `search_definitions()` joins the indexed sense-term table without exposing SQLite details. `segment()` evaluates known spans using authoritative full coverage, case flags, dynamic programming, and optional corpus rank, while retaining strict surface-case acceptance.
5. Runtime reads do not acquire missing data or write to the artifact.

## Dictionary relations

1. Build-time defensive extraction projects only the narrow Lexhint-owned Wiktextract fields. It retains redirects, `alt_of`, and `form_of` as typed relation candidates and drops unrelated upstream fields.
2. Schema 10 stores deterministic sense IDs, compact source provenance, and normalized `redirect`, `alternative`, `form_of`, `synonym`, `antonym`, `hypernym`, `hyponym`, and `related` headword rows only with the `dictionary` capability. Sense-level synonyms and antonyms remain attached to their exact senses, while incoming relations use the target index.
3. `relations(word)` performs bounded exact source lookup. `resolve_headword(word)` follows only the requested relation types. Neither operation is implicit in `entries()` or fuzzy search.

## Semantic evidence

1. `lexhint.semantics` maps supported raw source topics to stable `SemanticDomain` values at build time.
2. Context distances are measured from the target character span. Every lexical token overlapping a non-empty target is excluded. If no lexical token overlaps, the target is a virtual insertion boundary and no real token is discarded.
3. Nearby words are queried in batches. Domain weights receive configurable distance decay, with adjacent eligible tokens at distance 1.
4. Results preserve cue text, character spans, token distance, and contribution weight. The candidate cannot validate itself. Domain results are hints rather than sense-disambiguated semantic certainty, and missing evidence is not negative evidence.

The public dictionary API distinguishes sense-scoped relations from unsense-disambiguated headword relations and exposes `sense_by_id()` and `incoming_relations()`.

<!-- archledger: no accepted records for this section yet -->

# Deployment View

Lexhint is deployed as a local Python package and a local SQLite evidence artifact. There is no application server, worker, or persistent service.

- Consumers install the package and open an artifact with `Lexicon.from_path()` or the default `Lexicon` resolution.
- Artifact paths are selected by the caller or build workflow; CLI `--path` is an explicit override.
- `dictionary status` reports current row counts, schema, capabilities, source format, source contract, and provenance without rebuilding the artifact.
- A complete local artifact supports offline lexical, segmentation, dictionary, semantic, fuzzy, headword, relation, and definition-search reads when the corresponding capabilities are present.
- Generated artifacts contain source and hash provenance for dictionary and corpus inputs.
- Build downloads and replacements use temporary files and atomic rename.
- Generated external datasets are distributed separately from code according to `DATA_SOURCES.md`.

<!-- archledger: no accepted records for this section yet -->

# Cross-cutting Concepts

### Capability-specific schema

Schema metadata is explicit and self-describing. `language`, `locale`, `variant`, `schema_version`, and `dataset_version` remain separate dimensions. Locale is optional and does not create `en-GB` or `en-US` artifacts. Strict equality, not a compatibility range, controls SQLite access.

Schema 10 metadata is explicit and self-describing. `lexemes` is always present for lexical capability and stores lowercase, titlecase, and uppercase attestation flags exposed by `WordEvidence`. `lexeme_domains` exists only for `semantic`; rich `entries`, `senses`, `sense_topics`, and `headword_relations` exist only for `dictionary`; `lexeme_ngrams` exists for `search`; and `sense_search_terms` exists for `dictionary` plus `search`. Search and relation metadata record index and row counts, and projections remove claims for excluded structures. Schema 9 artifacts are rejected and must be rebuilt; schema 9 and schema 10 dataset families remain side by side on disk.

Managed dataset variants select capability subsets in a strict chain: `lexical`, `runtime` (`lexical,semantic`), `dictionary` (`lexical,semantic,dictionary`), and `rich` (`lexical,semantic,dictionary,search`). A dictionary projection supports full entry/sense/topic inspection, explicit relation lookup, rendering, semantic context, and completion while intentionally omitting fuzzy suggestion and indexed definition/reverse search. Only rich includes both search structures.

### Source contract and diagnostics

The build consumes a narrow Lexhint-owned TypedDict contract for the fields it intentionally retains: lexical identity, POS, senses, topics, forms, IPA sounds, etymology, examples, synonyms, antonyms, redirects, `alt_of`, and `form_of`. Translations, descendants, broader linkage taxonomies, audio URLs, IDs, raw glosses, categories, templates, and unknown fields are not persisted. Extraction diagnostics and the local inspection tool report retained and dropped fields without weakening defensive runtime checks.

### Provenance and data lifecycle

Metadata records `dictionary_source`, `dictionary_source_sha256`, `dictionary_source_format`, `dictionary_source_contract`, `frequency_source`, and `frequency_source_sha256`, alongside profile, capabilities, creation time, and builder version. Remote dictionary input is hashed while streamed. Automatic FrequencyWords sources are cached by pinned revision and language, validated against an atomic SHA-256 sidecar, and downloaded through temporary files followed by atomic rename.


The static dataset catalog is a small validated cache under the platform cache directory or `LEXHINT_CACHE_DIR`. Networked dataset operations send conditional refresh metadata and atomically replace catalog bytes only after schema and artifact validation. Transport failures reuse a valid cache, while malformed reachable catalogs remain errors. Offline `dataset available` and `dataset check` use cached catalog data; dataset installation and update remain networked operations.

`dataset available` exposes all catalog artifacts compatible with the running SQLite schema, including historical versions. `dataset check` compares the newest compatible artifact with every selected installed language and variant. `dataset update` processes all installed slots by default, installs and validates replacements atomically, and removes superseded versions only after successful installation. Lexicon construction and ordinary query operations remain local-only.
### Relation decision evidence

The schema 10 benchmark compares a pre-schema-10 relation layout with compact compound-key tables and immutable index finalization. On the smoke profile, the candidate measured 204,800 raw bytes and 36,558 gzip bytes versus 425,984 raw bytes and 96,183 gzip bytes for the baseline. Suggestion and definition-search timings were slower in this two-iteration run, so the measurements are comparative evidence rather than English-dataset estimates.

### Errors and offline behavior

Capability, coverage, schema, language, and missing-artifact failures have controlled public exceptions. Offline mode rejects every HTTP(S) build source and permits only local or already validated cached inputs. Frequency acquisition fails the build unless the caller explicitly selects `--no-frequency` or a custom source. Missing semantic evidence is not semantic negation.

### Verification and licensing

Tests cover read-only behavior, no-network guards, segmentation, case attestation, virtual-boundary semantic target anchoring, schema and capability validation, frequency policy, semantic target exclusion, CLI contracts, source extraction, relation extraction/API/CLI/projection, and the managed four-variant resolver chain. External dictionary and corpus data remain subject to the obligations documented in `DATA_SOURCES.md`.

Raw bulk Wiktextract input does not contain Kaikki postprocessed website `sense.id` values. Lexhint therefore ignores that field, retains sparse `senseid` and Wikidata provenance when available, and generates a versioned deterministic `lh1-<language>-<encoded>` sense ID. High-cardinality translations and derived graphs remain optional data rather than core tables.

## Explicit immutable managed dataset artifacts

Lexhint treats published datasets as explicit, immutable local artifacts rather than package-installed Python models. The dataset manager stores artifacts by normalized base language, capability variant, exact schema family, and exact release version under the persistent data directory. Downloads stream gzip data, verify manifest hashes, sizes, schema, language, coverage, and capabilities, then atomically install the database and sidecar metadata. Runtime Lexicon construction resolves only installed files and never contacts the network automatically. The highest-capability compatible installed variant is selected by default, while callers may pin a variant and release version.

Managed variants are capability presets: `runtime` is the recommended `lexical,semantic` artifact, `dictionary` is the `lexical,semantic,dictionary` projection for dictionary inspection without search indexes, and `rich` adds `search` for fuzzy suggestions and indexed definition/reverse search. The strict capability chain keeps automatic selection unambiguous.

# Architecture Decisions

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
- **Freeze schema 10 as an explicit compatibility boundary.** The structural contract, capability-aware validator, exact metadata version check, deterministic `lh1` identity, persisted JSON formats, and search-index version are part of the artifact contract. Incompatible changes require schema 11 and a full rebuild of all managed variants.

<!-- archledger: no accepted records for this section yet -->

# Quality Requirements

| Quality attribute | Architectural response                                                                                           | Observable scenario                                                                                |
| ----------------- | ---------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| Correctness       | Explicit schema and capability validation, case-aware lexemes, authoritative full coverage, and target exclusion | A candidate is never used as its own semantic cue and incompatible artifacts fail at construction. |
| Determinism       | Stable source projections, bounded weights, immutable build plans, and explicit result fields                    | Repeating a local query returns the same segments and evidence ordering.                           |
| Performance       | Indexed SQLite lookups, bounded context windows, batched nearby-word queries, and streamed builds                | A context query evaluates only the bounded local evidence window.                                  |
| Resilience        | Read-only runtime access, source hashes, temporary downloads, and atomic replacement                             | A failed build does not replace an existing artifact with partial output.                          |
| Maintainability   | Focused runtime and build modules, capability-specific schema, and boundary tests                                | Schema, extraction, semantic projection, storage, and CLI behavior can be checked independently.   |
| Compliance        | External resources remain separate from code and provenance is embedded in artifacts                             | A distributor can review data obligations before distributing generated artifacts.                 |

## Quality Requirements Overview

<!-- archledger: no accepted records for this section yet -->

## Quality Scenarios

<!-- archledger: no accepted records for this section yet -->

# Risks and Technical Debt

- **Upstream availability and format drift.** FrequencyWords and Wiktextract/Kaikki remain external inputs. Hash validation and source checks reduce silent corruption, but upstream changes can still prevent builds.
- **External data licensing.** Generated artifacts inherit obligations from their dictionary and corpus sources. Redistribution must follow `DATA_SOURCES.md`.
- **Heuristic segmentation.** Dynamic-programming segmentation is evidence, not linguistic analysis, and may need tuning for new languages or identifier styles.
- **Incomplete capability coverage.** A consumer cannot use dictionary or semantic operations when the artifact lacks those capabilities. Missing evidence must not be treated as semantic negation.
- **Schema evolution.** Incompatible schema or capability changes require rebuilding artifacts.
- **Scope boundary.** Lexhint does not pronounce text, tokenize all consumer inputs, or resolve interpretation precedence. Those responsibilities remain downstream.

## Risk Overview

<!-- archledger: no accepted records for this section yet -->

# Glossary

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

<!-- archledger: no accepted records for this section yet -->
