---
schema_version: 4
id: content-0005
kind: content
type: section
section: building_block_view
title: Building Block View
order: 50
status: accepted
version: 2
body_format: markdown
---

The package is a set of focused Python modules with the CLI as the outer adapter.

- `lexhint.cli` parses commands, resolves languages and flags, formats human output, and emits stable JSON.
- `lexhint.lexicon.Lexicon` resolves a vendored or cached gzip word list, loads it lazily, provides membership and rank, and segments compact text.
- `lexhint.dictionary.Dictionary` validates schema and language metadata, reads senses, and computes topic scores and context support.
- `lexhint.store` defines schema-v4 SQLite storage, normalization, semantic row extraction, lookup state, and partial-cache updates.
- `lexhint.kaikki` builds exact-word Kaikki URLs and streams JSONL responses for lazy fetches.
- `lexhint.builder` streams local or remote bulk JSONL and writes a complete SQLite index.
- `lexhint.download` defines supported languages, upstream URLs, cache paths, and atomic word-list downloads.
- `lexhint.models` contains the immutable evidence and operation-result dataclasses.

The public package exports the principal `Lexicon`, `Dictionary`, models, and version from `lexhint.__init__`. Tests exercise module boundaries with local fixtures and mocked network calls.
