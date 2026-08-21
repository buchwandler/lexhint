---
schema_version: 4
id: content-0006
kind: content
type: section
section: runtime_view
title: Runtime View
order: 60
status: accepted
version: 10
body_format: markdown
---

## Lexical lookup and segmentation

1. The consumer constructs `Lexicon` from one local SQLite artifact, resolved from the vendored, configured cache, or schema-aware managed dataset path when no override is supplied.
2. Construction validates exact schema version, base language, coverage, and explicit capabilities before queries.
3. An optional locale such as `GB` or `US` is runtime presentation state. It does not change artifact resolution or physical English dataset identity.
4. `word()` and `contains()` query dictionary-derived lexemes. `word()` exposes casing attestation already stored in the lexeme row. `segment()` evaluates known spans using authoritative full coverage, case flags, dynamic programming, and optional corpus rank, while retaining strict surface-case acceptance.
5. Runtime reads do not acquire missing data or write to the artifact.

## Semantic evidence

1. `lexhint.semantics` maps supported raw source topics to stable `SemanticDomain` values at build time.
2. Context distances are measured from the target character span. Every lexical token overlapping a non-empty target is excluded. If no lexical token overlaps, the target is a virtual insertion boundary and no real token is discarded.
3. Nearby words are queried in batches. Domain weights receive configurable distance decay, with adjacent eligible tokens at distance 1.
4. Results preserve cue text, character spans, token distance, and contribution weight. The candidate cannot validate itself. Domain results are hints rather than sense-disambiguated semantic certainty, and missing evidence is not negative evidence.
