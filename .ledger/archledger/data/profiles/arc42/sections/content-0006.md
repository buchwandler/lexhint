---
schema_version: 4
id: content-0006
kind: content
type: section
section: runtime_view
title: Runtime View
order: 60
status: accepted
version: 14
body_format: markdown
---

## Lexical lookup and segmentation

1. The consumer constructs `Lexicon` from one local SQLite artifact, resolved from the vendored, configured cache, or schema-aware managed dataset path when no override is supplied.
2. Construction validates exact schema version, base language, coverage, and explicit capabilities before queries.
3. An optional locale such as `GB` or `US` is runtime presentation state. It does not change artifact resolution or physical English dataset identity. Regional source tags are defined once in `languages.py` and used by runtime ordering.
4. `word()` and `contains()` query lexical keys. `complete()` performs bounded normalized prefix completion through exact lookup and indexed lexical range queries; it is not fuzzy correction. `suggest()` uses bounded n-gram candidates, `match_headwords()` uses safe glob/regex scans, and `search_definitions()` joins the indexed sense-term table without exposing SQLite details. `segment()` evaluates known spans using authoritative full coverage, case flags, dynamic programming, and optional corpus rank, while retaining strict surface-case acceptance.
5. Runtime reads do not acquire missing data or write to the artifact.

## Dictionary relations

1. Build-time defensive extraction projects only the narrow Lexhint-owned Wiktextract fields. It retains redirects, `alt_of`, and `form_of` as typed relation candidates and drops unrelated upstream fields.
2. Schema 9 stores normalized `redirect`, `alternative`, and `form_of` rows only with the `dictionary` capability. The `runtime` and `lexical` variants do not contain this table.
3. `relations(word)` performs bounded exact source lookup. `resolve_headword(word)` follows only the requested relation types. Neither operation is implicit in `entries()` or fuzzy search.

## Semantic evidence

1. `lexhint.semantics` maps supported raw source topics to stable `SemanticDomain` values at build time.
2. Context distances are measured from the target character span. Every lexical token overlapping a non-empty target is excluded. If no lexical token overlaps, the target is a virtual insertion boundary and no real token is discarded.
3. Nearby words are queried in batches. Domain weights receive configurable distance decay, with adjacent eligible tokens at distance 1.
4. Results preserve cue text, character spans, token distance, and contribution weight. The candidate cannot validate itself. Domain results are hints rather than sense-disambiguated semantic certainty, and missing evidence is not negative evidence.
