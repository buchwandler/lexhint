---
title: "Architecture Documentation"
version: 15
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
- `segment()` uses authoritative full coverage, case flags, dynamic programming, and optional corpus rank.
- `entries()` requires the `dictionary` capability.
- `context_domains()` and `supports_domain()` require `semantic` and full coverage.

Absence of semantic evidence is not semantic negation. Capability, coverage, schema, language, and missing-artifact failures have controlled public exceptions.

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
- The CLI resolves default cached or vendored artifacts for ordinary reads and exposes `dictionary status` for current SQL counts.
- Schema 7 metadata records schema version, language, coverage, profile, capabilities, creation time, builder version, and source provenance.
- `lexemes` is present for the lexical capability. Semantic and dictionary tables are capability-specific.
- Default builds select `lexical,semantic,dictionary` and automatic pinned full FrequencyWords enrichment.
- Frequency is enrichment, not a capability.
- External dictionary and corpus data remain separate from the Apache-2.0 code and retain their licensing obligations.

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

- `lexhint.lexicon.Lexicon` owns read-only artifact access, lexical lookup, segmentation, dictionary inspection, and semantic evidence queries.
- `lexhint.schema` defines schema and capability validation for the self-describing SQLite artifact.
- `lexhint.builder` creates fresh atomic artifacts from streamed source data and applies the immutable build plan.
- `lexhint.extract` converts source records into curated lexical and dictionary data.
- `lexhint.semantics` projects source topics into the stable `SemanticDomain` taxonomy.
- `lexhint.frequency` and `lexhint.sources` resolve corpus enrichment and source provenance.
- `lexhint.store` persists lexemes, domains, rich dictionary tables, metadata, and indexes.
- `lexhint.cli` exposes build and runtime operations in human-readable and JSON forms.

The public package exports `Lexicon` and `SemanticDomain` as the principal consumer interface. Build and source helpers remain available from their owning modules.

## Consumer interface

```python
from lexhint import Lexicon, SemanticDomain

lexicon = Lexicon.from_path("en.sqlite3")
segments = lexicon.segment("chatgpt")
text = "The compiler is 8.3.2."
start = text.index("8.3.2")
evidence = lexicon.supports_domain(
    text, target=(start, start + len("8.3.2")), domain=SemanticDomain.COMPUTING
)
```

The consumer decides what an unknown run, version, or candidate should mean. Lexhint ends at evidence.



<!-- archledger: no accepted records for this section yet -->

# Runtime View

## Lexical lookup and segmentation

1. The consumer constructs `Lexicon` from one local SQLite artifact, resolved from the vendored or configured cache path when no override is supplied.
2. Construction validates schema version, language, coverage, and explicit capabilities.
3. `word()` and `contains()` query dictionary-derived lexemes. `segment()` evaluates known spans using authoritative full coverage, case flags, dynamic programming, and optional corpus rank.
4. Runtime reads do not acquire missing data or write to the artifact.

## Semantic evidence

1. `lexhint.semantics` maps supported raw source topics to stable `SemanticDomain` values at build time.
2. Context tokenization excludes every token overlapping the target span.
3. Nearby words are queried in batches. Domain weights receive configurable distance decay.
4. Results preserve cue text, character spans, token distance, and contribution weight. The candidate cannot validate itself.



<!-- archledger: no accepted records for this section yet -->

# Deployment View

Lexhint is deployed as a local Python package and a local SQLite evidence artifact. There is no application server, worker, or persistent service.

- Consumers install the package and open an artifact with `Lexicon.from_path()` or the default `Lexicon` resolution.
- Artifact paths are selected by the caller or build workflow; CLI `--path` is an explicit override.
- `dictionary status` reports current row counts and metadata without rebuilding the artifact.
- A complete local artifact supports offline lexical, segmentation, dictionary, and semantic reads when the corresponding capabilities are present.
- Generated artifacts contain source and hash provenance for dictionary and corpus inputs.
- Build downloads and replacements use temporary files and atomic rename.
- Generated external datasets are distributed separately from code according to `DATA_SOURCES.md`.



<!-- archledger: no accepted records for this section yet -->

# Cross-cutting Concepts

### Capability-specific schema

Schema 7 metadata is explicit and self-describing. `lexemes` is always present for lexical capability. `lexeme_domains` exists only for `semantic`; each row stores bounded deterministic weight and source-topic provenance. Rich `entries`, `senses`, `sense_topics`, forms, and pronunciations exist only for `dictionary`. Old partial-cache schemas are rejected and must be rebuilt.

### Provenance and data lifecycle

Metadata records `dictionary_source`, `dictionary_source_sha256`, `frequency_source`, and `frequency_source_sha256`, alongside profile, capabilities, creation time, and builder version. Remote dictionary input is hashed while streamed. Automatic FrequencyWords sources are cached by pinned revision and language, validated against an atomic SHA-256 sidecar, and downloaded through temporary files followed by atomic rename.

### Errors and offline behavior

Capability, coverage, schema, language, and missing-artifact failures have controlled public exceptions. Offline mode rejects every HTTP(S) build source and permits only local or already validated cached inputs. Frequency acquisition fails the build unless the caller explicitly selects `--no-frequency` or a custom source. Missing semantic evidence is not semantic negation.

### Verification and licensing

Tests cover read-only behavior, no-network guards, segmentation, schema and capability validation, frequency policy, semantic target exclusion, CLI contracts, and source extraction. External dictionary and corpus data remain subject to the obligations documented in `DATA_SOURCES.md`.



## Explicit immutable managed dataset artifacts

Lexhint treats published datasets as explicit, immutable local artifacts rather than package-installed Python models. The dataset manager stores artifacts by normalized language, capability variant, and exact release version under the persistent data directory. Downloads stream gzip data, verify manifest hashes, sizes, schema, language, coverage, and capabilities, then atomically install the database and sidecar metadata. Runtime Lexicon construction resolves only installed files and never contacts the network automatically. The highest-capability compatible installed variant is selected by default, while callers may pin a variant and release version.

# Architecture Decisions

The current architecture records these decisions.

- **Use a self-describing SQLite artifact.** Schema, language, coverage, profile, capabilities, and provenance are validated at runtime.
- **Separate lexical, semantic, and dictionary capabilities.** Consumers can select the evidence they need without allowing data from an older artifact to leak into a fresh build.
- **Treat frequency as enrichment.** Corpus rank improves segmentation and commonness evidence but does not define lexical capability.
- **Build fresh artifacts atomically.** Capability-specific tables are created from the resolved build plan and replacements cannot expose partial output.
- **Use stable semantic domains.** Raw source topics are projected into a small deterministic taxonomy at build time.
- **Exclude the candidate from context evidence.** A target token cannot validate its own interpretation.
- **Keep the runtime read-only and offline by default.** Acquisition belongs to explicit build workflows.
- **Keep a narrow consumer boundary.** Lexhint supplies evidence; downstream consumers own interpretation and speech rendering.

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
