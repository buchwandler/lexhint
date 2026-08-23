---
schema_version: 4
id: content-0005
kind: content
type: section
section: building_block_view
title: Building Block View
order: 50
status: accepted
version: 14
body_format: markdown
---

The package is organized around a local artifact runtime and focused build modules.

- `lexhint.lexicon.Lexicon` owns read-only artifact access, lexical lookup, prefix completion, fuzzy suggestions, headword matching, indexed definition search, segmentation, dictionary inspection, and semantic evidence queries.
- `lexhint.schema` defines schema and capability validation for the self-describing SQLite artifact.
- `lexhint.builder` creates fresh atomic artifacts from streamed source data and applies the immutable build plan.
- `lexhint.extract` converts source records into curated lexical and dictionary data.
- `lexhint.semantics` projects source topics into the stable `SemanticDomain` taxonomy.
- `lexhint.frequency` and `lexhint.sources` resolve corpus enrichment and source provenance.
- `lexhint.store` persists lexemes, domains, rich dictionary tables, search indexes, metadata, and indexes.
- `lexhint.cli` exposes build and runtime operations in human-readable and JSON forms.

The public package exports `Lexicon`, `DictionarySearchHit`, and `SemanticDomain` as the principal consumer interface. It also exports `SCHEMA_VERSION`, `DATASET_VARIANTS`, `DATASET_VARIANT_NAMES`, `DEFAULT_DATASET_VARIANT`, and `supported_base_languages()` for the separate dataset publisher contract. Build and source helpers remain available from their owning modules.

## Consumer interface

```python
from lexhint import Lexicon, SemanticDomain

lexicon = Lexicon.from_path("en.sqlite3")
completions = lexicon.complete("comp")
suggestions = lexicon.suggest("complier")
headwords = lexicon.match_headwords("comp*", syntax="glob")
hits = lexicon.search_definitions("computer program", fields=("glosses",), match="all")
segments = lexicon.segment("chatgpt")
text = "The compiler is 8.3.2."
start = text.index("8.3.2")
evidence = lexicon.supports_domain(
    text, target=(start, start + len("8.3.2")), domain=SemanticDomain.COMPUTING
)
```

The consumer decides what an unknown run, version, or candidate should mean. Lexhint ends at evidence.
