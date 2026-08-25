---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 2
entry_id: entry-0005
release_version: v0.4.0
kind: changed
summary:
  Changed schema 10 into an exact artifact boundary with side-by-side schema
  families and full managed-variant rebuilds
status: accepted
audience: null
scopes: []
source_refs:
  - tl:task-0025
paths:
  - lexhint/schema_contract.py
  - lexhint/datasets.py
  - docs/architecture.md
  - RELEASING.md
issues: []
prs: []
sources: []
contributors: []
breaking: true
internal: false
order: 5
---

Schema 9 datasets are incompatible with schema 10. The release contract covers deterministic lh1 sense IDs, separate source provenance, compact immutable storage, normalized dictionary relations, and finalization validation.
