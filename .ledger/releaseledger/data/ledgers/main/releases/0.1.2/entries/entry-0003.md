---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0003
release_version: 0.1.2
kind: added
summary:
  Added deterministic local lexical prefix completion through Lexicon.complete()
  and lexhint complete
status: accepted
audience: null
scopes: []
source_refs:
  - tl:task-0016
paths:
  - lexhint/lexicon.py
  - lexhint/cli.py
  - tests/test_completion.py
issues: []
prs: []
sources: []
contributors: []
breaking: false
internal: false
order: 3
---

Completion returns normalized lexical keys with exact-match priority, full-prefix semantics, deterministic corpus-aware ordering, and indexed SQLite range lookup. It does not perform spelling correction.
