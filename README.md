# lexhint

Lexhint is a local lexical-evidence engine backed by self-describing SQLite language databases. It provides lexical membership, optional corpus commonness, compact-string segmentation, semantic-domain evidence, and optional rich dictionary entries.

Lexhint does not normalize or speak text. Word boundaries, acronyms, URLs, numbers, versions, and pronunciation policy belong to the consuming application.

## Install

```bash
python -m pip install -e ".[dev]"
```

## Runtime

Open a local artifact with `Lexicon`:

```python
from lexhint import Lexicon

lexicon = Lexicon.from_path("en.sqlite3")
info = lexicon.word("compiler")
print(info.known, info.frequency_rank)
print(lexicon.segment("compilerword"))
```

Runtime access is local-only, deterministic, read-only, and never fetches missing entries or mutates the database. `segment()` and semantic context operations require full authoritative coverage.

The public runtime operations are:

```python
lexicon.word("compiler")
lexicon.contains("compiler")
lexicon.segment("chatgpt")
lexicon.context_domains(text, target=(start, end))
lexicon.supports_domain(text, target=(start, end), domain="computing")
lexicon.entries("compiler")  # rich artifacts only
```

Dictionary membership is authoritative. Frequency rank and count enrich existing lexemes but never create corpus-only words. Case evidence is retained, so an uppercase-only `GPT` entry does not validate lowercase `gpt`.

Semantic results are explainable `DomainEvidence` values containing score and nearby `ContextCue` records. The target span is always excluded, and missing evidence is not negative evidence.

## Build an artifact

The default build creates a full `lexical,semantic,dictionary` artifact and automatically acquires the pinned full FrequencyWords source:

```bash
lexhint dictionary build en
```

Use a local or remote dictionary source and explicit build policies when needed:

```bash
lexhint dictionary build en --source ./raw-wiktextract-data.jsonl.gz
lexhint dictionary build en --capabilities lexical,semantic --no-frequency
lexhint dictionary build en --profile runtime
lexhint dictionary build en --frequency-source ./en_full.txt
lexhint dictionary build en --refresh-frequency
lexhint --offline dictionary build en --source ./raw-wiktextract-data.jsonl.gz
```

Capabilities are canonicalized in the order `lexical,semantic,dictionary`. `semantic` and `dictionary` require `lexical`. Profiles are shortcuts: `runtime` means `lexical,semantic`, and `rich` means `lexical,semantic,dictionary`.

Frequency enrichment is independent of capabilities. Use `--no-frequency` for a valid lexical artifact without corpus data. Automatic sources are cached under `~/.cache/lexhint/sources/frequencywords/<revision>/`, or an equivalent XDG/`LEXHINT_CACHE_DIR` location. Builds record source URLs, revisions, hashes, schema, capabilities, and builder metadata. Build configuration and progress are written to stderr, while the final result, including JSON, is written to stdout.

## CLI queries

```bash
lexhint word compiler
lexhint segment chatgpt
lexhint context "The compiler is 8.3.2." --target 16:21
lexhint dictionary word compiler
lexhint dictionary status
```

Use `--json` for stable machine-readable output. `dictionary status` reports current SQL row counts, capabilities, provenance, size, and build metadata without rebuilding. Use `--path` as an advanced override when inspecting a specific artifact. Rich dictionary lookup reports a controlled capability error for compact runtime artifacts.

## Data and scope

The builder consumes Wiktextract-compatible JSONL, commonly from Kaikki, and FrequencyWords full files for optional corpus enrichment. See [DATA_SOURCES.md](DATA_SOURCES.md) for source and licensing information.

Lexhint does not implement Spokenform integration, dataset publication, URL parsing, speech rendering, or consumer-specific interpretation rules. The separate `buchwandler/lexhint-datasets` repository is outside this project.

## Development

```bash
pytest -q
ruff check .
mypy lexhint
```
