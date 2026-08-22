---
schema_version: 2
object_type: release_entry
versioning:
  schema_version: 1
  revision: 1
entry_id: entry-0002
release_version: 0.1.3
kind: changed
summary:
  Added automatic color styling for interactive human dictionary output with
  explicit opt-out controls
status: accepted
audience: null
scopes: []
source_refs:
  - git:0e7f8d4d435222a1f3f8109d7089b6fd181315ee
paths:
  - lexhint/terminal.py
  - lexhint/cli.py
  - lexhint/render.py
  - tests/test_cli_dictionary_output.py
  - tests/test_dictionary_render.py
  - README.md
issues: []
prs: []
sources: []
contributors: []
breaking: false
internal: false
order: 2
---

ANSI color is enabled only for interactive non-JSON output and can be disabled with --no-color or NO_COLOR; rendering preserves visible-width constraints
