---
schema_version: 4
id: content-0002
kind: content
type: section
section: architecture_constraints
title: Architecture Constraints
order: 20
status: accepted
version: 5
body_format: markdown
---

The architecture is constrained by the public package contract and by the nature of its external data sources.

- Python 3.10 or newer is required.
- The runtime has no third-party Python dependencies. Optional development tools are configured in `pyproject.toml`.
- The package uses a flat `lexhint/` source layout and setuptools with dynamic `setuptools-scm` versioning.
- FrequencyWords and Wiktionary/Wiktextract/Kaikki are external resources. They are downloaded or built separately, pinned or hashed when reproducibility matters, and are not assumed to be bundled.
- Runtime caches are user-local and can be relocated with `LEXHINT_CACHE_DIR` or `XDG_CACHE_HOME`.
- Dictionary data is stored in a curated hierarchical schema-v5 SQLite index, not as a full Wiktionary mirror.
- External dictionary text and generated data carry attribution and license obligations documented in `DATA_SOURCES.md`.
- The library must remain useful offline when the required local word list or dictionary coverage is available.
- Git-less source archives use a non-release version fallback and must not masquerade as a published release.
