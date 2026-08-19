---
title: "Architecture Documentation"
version: 4
generator: "archledger 0.4.0"
arc42_template_version: "9.0-EN"
---

# Architecture Documentation

Generated from archledger records. Do not edit this generated file directly.

# Introduction and Goals

`lexhint` is a Python library and CLI that supplies lexical and dictionary-derived semantic evidence to text-normalization and speech-front-end applications such as `spokenform`. It deliberately does not verbalize text or own speech policy.

## Requirements overview

- Determine common-word membership and frequency rank for supported languages.
- Segment compact identifiers and domain labels into known words and unknown runs.
- Extract compact dictionary senses and explicit semantic topics from Wiktextract/Kaikki data.
- Provide candidate-aware context evidence while excluding the candidate token itself.
- Support both lazy per-word acquisition and complete streamed dictionary builds.
- Expose human-readable CLI output and stable JSON output for automation.

## Quality goals

- Keep the runtime dependency-free beyond the Python standard library.
- Make network use explicit, bounded, cacheable, and avoidable with `--offline`.
- Preserve deterministic normalization, segmentation, storage, and JSON behavior, with
  source and snapshot identities recorded for external data.
- Keep external data separate from the Apache-2.0 code distribution.

## Stakeholders

- Speech and text-normalization consumers need small, explainable evidence objects.
- Application developers need a simple Python API and CLI.
- Maintainers need reproducible builds, tests, and safe data-source handling.
- Distributors need clear boundaries between code licensing and external dictionary data.

## Requirements Overview

<!-- archledger: no accepted records for this section yet -->

## Quality Goals

<!-- archledger: no accepted records for this section yet -->

## Stakeholders

<!-- archledger: no accepted records for this section yet -->

# Architecture Constraints

The architecture is constrained by the public package contract and by the nature of its external data sources.

- Python 3.10 or newer is required.
- The runtime has no third-party Python dependencies. Optional development tools are configured in `pyproject.toml`.
- The package uses a flat `lexhint/` source layout and setuptools with dynamic `setuptools-scm` versioning.
- FrequencyWords and Wiktionary/Wiktextract/Kaikki are external resources. They are downloaded or built separately, pinned or hashed when reproducibility matters, and are not assumed to be bundled.
- Runtime caches are user-local and can be relocated with `LEXHINT_CACHE_DIR` or `XDG_CACHE_HOME`.
- Dictionary data is stored in a compact schema-v4 SQLite index, not as a full Wiktionary mirror.
- External dictionary text and generated data carry attribution and license obligations documented in `DATA_SOURCES.md`.
- The library must remain useful offline when the required local word list or dictionary coverage is available.
- Git-less source archives use a non-release version fallback and must not masquerade as a published release.

<!-- archledger: no accepted records for this section yet -->

# Context and Scope

`lexhint` sits between lexical resources and a speech or text-normalization consumer.

## Business context

```text
FrequencyWords ──> common-word evidence ─┐
                                         ├─> lexhint ──> evidence objects ──> spokenform
Wiktionary/Kaikki ─> senses and topics ──┘
```

The consumer decides how evidence affects pronunciation. For example, `lexhint` can report that `chat` is known and `gpt` is an unknown run, or that nearby `compiler` evidence supports a `computing` interpretation. It does not implement `Am -> A minor`, version pronunciation, URL symbol names, or other speech policy.

## Technical context

- Inputs are FrequencyWords text files and Wiktextract-compatible JSONL, either local or remote.
- The CLI and Python API read resources through the cache layer.
- The application process owns in-memory lexical data and read-only SQLite dictionary access.
- Lazy dictionary lookups request only exact Kaikki word pages and persist compact results.
- Full builds stream the bulk JSONL source line by line into SQLite.
- Outputs are dataclasses, tuples, CLI text, or stable JSON. No service endpoint or daemon is required.

## Business Context

<!-- archledger: no accepted records for this section yet -->

## Technical Context

<!-- archledger: no accepted records for this section yet -->

# Solution Strategy

The solution is organized around a small, explicit evidence pipeline.

## Strategy items

1. Keep common-word lexicon evidence independent from semantic dictionary evidence. Technical dictionary cues must not be limited by a 50k frequency list.
2. Normalize Unicode to NFC and use case-folded lookup keys while retaining display spelling for dictionary results.
3. Load word lists lazily and use dynamic programming for compact-label segmentation. Unknown characters are merged into runs, and obscure two-letter matches are rejected to preserve initialisms. URL syntax remains the caller's responsibility.
4. Keep dictionary indexes compact. Store normalized word keys, display spelling, part of speech, glosses, and explicit topics only.
5. Make partial dictionary coverage incremental. Cache successful empty and not-found lookups and fetch only missing nearby context words when network access is explicitly allowed. Distinguish live partial caches from reproducible full snapshots.
6. Exclude the target span from topic scoring so a candidate cannot validate itself. Score nearby explicit topics with a bounded token window and distance decay.
7. Use a streaming bulk builder for complete offline coverage and atomic replacement of the resulting SQLite file.
8. Keep the integration boundary narrow. `spokenform` consumes evidence but remains responsible for interpretation and speech rendering.

## Strategy Items

<!-- archledger: no accepted records for this section yet -->

# Building Block View

The package is a set of focused Python modules with the CLI as the outer adapter.

- `lexhint.cli` parses commands, resolves languages and flags, formats human output, and emits stable JSON.
- `lexhint.lexicon.Lexicon` resolves an explicit, vendored, or cached gzip word list, loads it lazily, provides membership and rank, and segments compact text. Inline words are supported for isolated consumers and tests.
- `lexhint.dictionary.Dictionary` validates schema and language metadata, reads senses, and computes soft `TopicEvidence` with structured `ContextCue` values. `from_path()` can infer the language from a self-describing index.
- `lexhint.store` defines schema-v4 SQLite storage, normalization, semantic row extraction, lookup state, and partial-cache updates.
- `lexhint.kaikki` builds exact-word Kaikki URLs and streams JSONL responses for lazy fetches.
- `lexhint.builder` streams local or remote bulk JSONL and writes a complete SQLite index.
- `lexhint.download` defines supported languages, upstream URLs, cache paths, and atomic word-list downloads.
- `lexhint.models` contains the immutable runtime evidence and advanced operation-result dataclasses.

The public package exports only the principal runtime `Lexicon`, `Dictionary`, evidence models, exceptions, and version from `lexhint.__init__`. Build/download helpers remain importable from their owning advanced modules. Tests exercise module boundaries with local fixtures and mocked network calls.

<!-- archledger: no accepted records for this section yet -->

# Runtime View

## Word membership and segmentation

1. The CLI or API selects a language and constructs `Lexicon`.
2. The lexicon resolves inline words, an explicitly requested path, a vendored resource, or a user cache and loads file-backed words on first use. Missing resources are fetched only when `auto_fetch` is enabled.
3. `rank` returns one-based source order. `segment` evaluates candidate word spans, rewards longer and frequent words, penalizes unknown characters, and merges adjacent unknown spans.
4. The result is a tuple of `LexicalSegment` values. `in_lexicon` reports lexical-resource evidence only; it does not select pronunciation.

## Lazy dictionary context

1. `Dictionary` opens or initializes a schema-v4 partial SQLite cache, or opens a full index, and validates language and coverage metadata. `from_path()` can infer the language from that metadata.
2. Context tokenization finds nearby word tokens and identifies the target token by overlap or nearest span.
3. The target token is excluded. Missing nearby words are fetched individually only when `fetch_missing` is enabled and offline mode is not active; `refresh` explicitly revisits cached words.
4. Stored explicit topics are aggregated with distance decay into structured cues. `topic_scores` supports bounded windows and result limits, while `supports` returns `TopicEvidence` only when the requested topic reaches the threshold. Missing evidence is not negative evidence.

## Bulk dictionary build

The builder reads a local path or HTTP(S) source through a text stream, filters entries by `lang_code`, retains senses with glosses or topics, commits incrementally, records source identity/hash and build statistics, labels local full indexes with a SHA-256 snapshot and remote full indexes as live, runs `ANALYZE`, and atomically replaces the target database.

<!-- archledger: no accepted records for this section yet -->

# Deployment View

`lexhint` is deployed as a local Python package and command-line executable. There is no application server, worker, or persistent service.

- The package is installed from a wheel or source distribution and exposes the `lexhint` entry point.
- Vendored word lists or dictionaries, when deliberately included, are package data under `lexhint/data`.
- Otherwise, word lists live under the user cache at `words/<language>.txt.gz` with a provenance sidecar at `words/<language>.metadata.json`, and dictionaries at `dictionaries/<language>.sqlite3`.
- FrequencyWords downloads use a pinned upstream revision and validate the normalized cache against its sidecar.
- Lazy dictionary downloads use exact Kaikki word-page URLs.
- Bulk dictionary builds may read the official Kaikki raw JSONL URL or a local compatible file.
- `--offline` prevents missing dictionary data from being fetched. A complete local index supports fully offline context queries.
- Temporary files are created beside cache targets and atomically renamed into place, limiting partially written resources.
- Code-only release artifacts do not include user caches or generated external datasets.

<!-- archledger: no accepted records for this section yet -->

# Cross-cutting Concepts

### Normalization and identity

Unicode NFC normalization is used for stored display values and case folding for lookup keys. Dictionary rows retain display spelling so case-sensitive variants can be preferred without changing lookup identity.

### Data lifecycle and caching

Word lists are immutable normalized gzip files with a JSON provenance sidecar containing the pinned source revision, normalized SHA-256, and word count. Partial dictionaries maintain lookup status and timestamps so empty and not-found results are not repeatedly requested; their metadata identifies them as live partial caches. Full coverage is authoritative and does not trigger lazy fetches; local full indexes record a reproducible source snapshot identity. Schema compatibility is checked at runtime; partial schema-v3 caches are invalidated, while full incompatible indexes require a rebuild.

### Errors and offline behavior

Resource absence, malformed input, network failures, not-found results, incompatible metadata, and offline misses have distinct controlled exceptions. The CLI turns them into concise messages or JSON errors with actionable hints.

### Interfaces and observability

Python APIs return immutable dataclasses and tuples. CLI JSON serializes explicit fields, structured context cues, and build statistics. Progress reporting is sent to stderr and is used only for interactive bulk builds.

### Verification and licensing

Tests cover segmentation, parsing, schema behavior, lazy fetching, target exclusion, and CLI contracts using fixtures and mocked network access. External data provenance and redistribution duties are maintained separately in `DATA_SOURCES.md`.

<!-- archledger: no accepted records for this section yet -->

# Architecture Decisions

The current architecture records these decisions.

- **Separate lexical and semantic resources.** Frequency rank answers common-word questions; dictionary senses answer semantic-context questions. Combining them would discard useful technical vocabulary.
- **Use compact SQLite rather than hand-maintained context JSON.** SQLite supports incremental word caching, indexed lookup, metadata validation, and complete offline indexes without mirroring raw Wiktionary data.
- **Use lazy fetch by default in the Python API.** Normal local reads do not unexpectedly access the network. Explicit CLI operations or `fetch_missing=True` opt into acquisition.
- **Distinguish live data from reproducible snapshots.** Partial/live caches and remote full builds remain useful for interactive work; local full indexes carry a source hash and are the reproducible deployment/benchmark boundary.
- **Keep the runtime API narrow.** Build and download infrastructure remains available from advanced modules without becoming accidental top-level package contracts.
- **Exclude the candidate from its own context evidence.** This prevents a target token from falsely validating an interpretation based on its own dictionary topics.
- **Stream bulk sources.** Kaikki data is too large to require a temporary in-memory or duplicate raw copy; the builder processes it line by line.
- **Keep runtime dependencies to the standard library.** `urllib`, `sqlite3`, gzip, and dataclasses provide the required portability for a small library.
- **Use a narrow consumer boundary.** Speech pronunciation rules stay in the downstream speech layer instead of being duplicated in lexical infrastructure.

<!-- archledger: no accepted records for this section yet -->

# Quality Requirements

| Quality attribute | Architectural response                                                                                                 | Observable scenario                                                                     |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| Correctness       | NFC and case-folded keys, display-aware dictionary selection, explicit language filtering, and target exclusion        | A candidate token is never used as its own context cue; unrelated context fails closed. |
| Determinism       | Stable source ordering, one-based ranks, bounded scoring parameters, immutable result models, and explicit JSON fields | Repeating a local query returns the same rank, segments, senses, and topic ordering.    |
| Performance       | Lazy resource loading, indexed SQLite word lookup, bounded context windows, and streaming bulk builds                  | A context query fetches only nearby missing non-target tokens.                          |
| Portability       | Python 3.10+, standard-library runtime, local files, and configurable cache roots                                      | The package runs without a service or third-party runtime installation.                 |
| Resilience        | Atomic resource replacement, cached empty lookups, offline mode, and controlled exceptions                             | A transient or unavailable network does not corrupt an existing cache.                  |
| Maintainability   | Focused modules, compact public models, documented data provenance, and boundary tests                                 | Storage, network parsing, segmentation, and CLI behavior can be tested independently.   |
| Compliance        | External resources remain separate from code and their licenses are documented                                         | A distributor can review data obligations before vendoring generated indexes.           |

## Quality Requirements Overview

<!-- archledger: no accepted records for this section yet -->

## Quality Scenarios

<!-- archledger: no accepted records for this section yet -->

# Risks and Technical Debt

- **Upstream availability and format drift.** FrequencyWords and Kaikki are external services. URL, JSONL, or source-shape changes can prevent acquisition. Validation and controlled download errors reduce silent corruption, but source compatibility still needs monitoring.
- **External data licensing.** Generated dictionary indexes inherit obligations from Wiktionary, Wiktextract, Kaikki, and source corpora. Redistribution must follow `DATA_SOURCES.md`; the architecture intentionally does not hide this risk.
- **Heuristic segmentation.** Dynamic-programming scores and the two-letter guard are practical heuristics, not linguistic analysis. New languages or identifier styles may require tuning and more representative evaluation data.
- **Incomplete local coverage.** Lazy caches only know requested words, and no external network is available in offline mode. Consumers must handle absent evidence rather than treating it as a negative semantic result.
- **Schema evolution.** SQLite metadata and migration behavior are versioned, but full indexes may require explicit rebuilds after incompatible changes.
- **Limited production telemetry.** The library reports local results and build statistics but does not collect usage or upstream health metrics. Operational monitoring belongs to the embedding application.
- **Scope boundary.** `lexhint` does not pronounce text, resolve all language morphology, or perform general word-sense disambiguation. Those capabilities remain downstream or future work.

## Risk Overview

<!-- archledger: no accepted records for this section yet -->

# Glossary

- **Lexicon:** A frequency-ranked list used for common-word membership and identifier segmentation.
- **LexicalSegment:** An immutable result identifying a compact-label span, with `in_lexicon` evidence and an optional frequency rank. It does not decide pronunciation.
- **Dictionary sense:** A compact word entry containing display spelling, part of speech, glosses, and explicit topics.
- **Topic:** Semantic metadata supplied by Wiktextract/Kaikki and used as context evidence.
- **Context cue:** A nearby source token with span, distance, and decay weight contributing to a topic score.
- **Topic evidence:** Soft diagnostic topic score and structured cue list showing that nearby non-target words support a requested interpretation. No evidence is not negative evidence.
- **Partial coverage:** A live schema-v4 dictionary containing only explicitly looked-up word pages and their lookup statuses.
- **Full coverage:** A schema-v4 dictionary built from a complete compatible JSONL source. It is authoritative for local reads; local source builds record a reproducible snapshot hash.
- **Target span:** The source character interval whose candidate interpretation is being evaluated. It is excluded from context evidence.
- **Kaikki:** The upstream publication used for exact-word and bulk Wiktextract-derived dictionary data.
- **FrequencyWords:** The upstream 50k frequency lists used to provide common-word ranks.
- **Spokenform:** The downstream speech/text-normalization layer that consumes lexhint evidence and owns pronunciation policy.

<!-- archledger: no accepted records for this section yet -->
