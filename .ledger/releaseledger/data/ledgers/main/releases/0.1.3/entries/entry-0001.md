---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0001
release_version: 0.1.3
kind: added
summary:
  Added deterministic normalized lexical prefix completion through Lexicon.complete()
  and the complete CLI command
status: accepted
audience: null
scopes: []
source_refs:
  - git:f2f1c7838f01adbc79eaf2481aa968851acb1a6d
  - git:9946e356111481e41352b0167c01f88a299d69f5
paths:
  - lexhint/lexicon.py
  - lexhint/cli.py
  - tests/test_completion.py
  - README.md
  - docs/architecture.md
issues: []
prs: []
sources: []
contributors: []
breaking: false
internal: false
order: 1
---

Completion returns exact matches first, then full-prefix matches ordered by corpus rank when available or lexically otherwise; it is local, read-only, and does not perform spelling correction
