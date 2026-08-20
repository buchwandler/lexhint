---
schema_version: 4
id: content-0006
kind: content
type: section
section: runtime_view
title: Runtime View
order: 60
status: accepted
version: 5
body_format: markdown
---

## Word membership and segmentation

1. The CLI or API selects a language and constructs `Lexicon`.
2. The lexicon resolves inline words, an explicitly requested path, a vendored resource, or a user cache and loads file-backed words on first use. Missing resources are fetched only when `auto_fetch` is enabled.
3. `rank` returns one-based source order. `segment` evaluates candidate word spans, rewards longer and frequent words, penalizes unknown characters, and merges adjacent unknown spans.
4. The result is a tuple of `LexicalSegment` values. `in_lexicon` reports lexical-resource evidence only; it does not select pronunciation.

## Lazy dictionary context

1. `Dictionary` opens or initializes a schema-v5 partial SQLite cache, or opens a full index, and validates language and coverage metadata. `from_path()` can infer the language from that metadata.
2. Context tokenization finds nearby word tokens and identifies the target token by overlap or nearest span.
3. The target token is excluded. Missing nearby words are fetched individually only when `fetch_missing` is enabled and offline mode is not active; `refresh` explicitly revisits cached words.
4. Stored explicit topics are aggregated with distance decay into structured cues. `topic_scores` supports bounded windows and result limits, while `supports` returns `TopicEvidence` only when the requested topic reaches the threshold. Missing evidence is not negative evidence.

## Bulk dictionary build

The builder reads a local path or HTTP(S) source through a text stream, filters entries by `lang_code`, converts entries with the shared curated extractor, commits incrementally, records source identity/hash and build statistics, labels local full indexes with a SHA-256 snapshot and remote full indexes as live, runs `ANALYZE`, and atomically replaces the target database.
