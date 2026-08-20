---
schema_version: 4
id: content-0005
kind: content
type: section
section: building_block_view
title: Building Block View
order: 50
status: accepted
version: 5
body_format: markdown
---

The package is a set of focused Python modules with the CLI as the outer adapter.

- `lexhint.cli` parses commands, resolves languages and flags, formats human output, and emits stable JSON.
- `lexhint.lexicon.Lexicon` resolves an explicit, vendored, or cached gzip word list, loads it lazily, provides membership and rank, and segments compact text. Inline words are supported for isolated consumers and tests.
- `lexhint.dictionary.Dictionary` validates schema and language metadata, reads grouped entries, and computes soft `TopicEvidence` with structured `ContextCue` values. `from_path()` can infer the language from a self-describing index.
- `lexhint.extract` converts Kaikki mappings into the curated immutable entry model shared by lazy and bulk ingestion.
- `lexhint.store` defines schema-v5 SQLite storage, rich entry persistence, normalized topic indexing, lookup state, and partial-cache updates.
- `lexhint.kaikki` builds exact-word Kaikki URLs and streams JSONL responses for lazy fetches.
- `lexhint.builder` streams local or remote bulk JSONL and writes a complete SQLite index.
- `lexhint.download` defines supported languages, upstream URLs, cache paths, and atomic word-list downloads.
- `lexhint.models` contains the immutable runtime evidence and advanced operation-result dataclasses.

The public package exports only the principal runtime `Lexicon`, `Dictionary`, evidence models, exceptions, and version from `lexhint.__init__`. Build/download helpers remain importable from their owning advanced modules. Tests exercise module boundaries with local fixtures and mocked network calls.
