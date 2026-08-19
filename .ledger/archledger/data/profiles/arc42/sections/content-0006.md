---
schema_version: 4
id: content-0006
kind: content
type: section
section: runtime_view
title: Runtime View
order: 60
status: accepted
version: 3
body_format: markdown
---

## Word membership and segmentation

1. The CLI or API selects a language and constructs `Lexicon`.
2. The lexicon resolves a vendored resource, user cache, or explicitly requested path and loads it on first use.
3. `rank` returns one-based source order. `segment` evaluates candidate word spans, rewards longer and frequent words, penalizes unknown characters, and merges adjacent unknown spans.
4. The result is a tuple of `LexicalSegment` values. `in_lexicon` reports lexical-resource evidence only; it does not select pronunciation.

## Lazy dictionary context

1. `Dictionary` opens or initializes a schema-v4 partial SQLite cache and validates language and coverage metadata.
2. Context tokenization finds nearby word tokens and identifies the target token by overlap or nearest span.
3. The target token is excluded. Missing nearby words are fetched individually only when `fetch_missing` is enabled and offline mode is not active.
4. Stored explicit topics are aggregated with distance decay. `supports` returns `TopicEvidence` only when the requested topic reaches the threshold. Missing evidence is not negative evidence.

## Bulk dictionary build

The builder reads a local path or HTTP(S) source through a text stream, filters entries by `lang_code`, retains senses with glosses or topics, commits incrementally, records source identity/hash and build statistics, runs `ANALYZE`, and atomically replaces the target database.
