# lexhint

Lexhint is a local lexical-evidence engine backed by self-describing SQLite language databases. It provides lexical membership, optional corpus commonness, compact-string segmentation, semantic-domain evidence, and optional rich dictionary entries.

Lexhint does not normalize or speak text. Word boundaries, acronyms, URLs, numbers, versions, and pronunciation policy belong to the consuming application.

## Install

```bash
python -m pip install lexhint
```

Lexhint supports Python 3.10 through 3.14. The Python package contains code only, so install a dataset explicitly after installing the package. Published datasets are maintained separately in the [lexhint-datasets repository](https://github.com/buchwandler/lexhint-datasets), with their own licensing and provenance.

## Quick start

Install the normal English runtime artifact, inspect it, and query it locally:

```bash
python -m pip install lexhint
lexhint dataset download en
lexhint dataset list
lexhint word compiler -l en
lexhint context "The compiler is 8.3.2." -l en --target 16:21
lexhint complete comp -l en
```

`lexhint dataset download` is the only networked step. `Lexicon`, query commands, and dataset inventory commands use installed files and do not silently contact GitHub.

The download default is the `runtime` variant (`lexical,semantic`). Optional variants are:

- `lexical` for membership, frequency, and segmentation;
- `runtime` for lexical and semantic context evidence;
- `rich` for lexical, semantic, and dictionary inspection.

Install several variants side by side:

```bash
lexhint dataset download en --variant rich
lexhint dataset list --language en
lexhint dictionary word love -l en --variant rich
lexhint dataset remove en --variant rich
```

For reproducibility, install and select an exact release:

```bash
lexhint dataset download en --variant runtime --version 2026.08.20
```

The managed store uses `LEXHINT_DATA_DIR` when set, or the platform data directory otherwise. Artifacts are stored by base language, variant, exact SQLite schema, and dataset version. A local-build alternative is available with `lexhint dictionary build`; pass its output with `--path` when querying.

For a small local artifact without FrequencyWords enrichment, build from the repository fixture with `lexhint dictionary build en --source tests/fixtures/kaikki-mini.jsonl --output /tmp/lexhint-en.sqlite3 --no-frequency` and pass `--path /tmp/lexhint-en.sqlite3` to the query commands.

## 1. Common-word lexicon

Open the highest-capability installed artifact with `Lexicon`, or select a variant/version explicitly:

```python
from lexhint import Lexicon

lexicon = Lexicon("en")  # highest installed compatible variant
runtime = Lexicon("en", variant="runtime")
pinned = Lexicon("en", variant="runtime", dataset_version="2026.08.20")
info = lexicon.word("compiler")
print(info.known, info.frequency_rank, info.has_lowercase, info.has_titlecase, info.has_uppercase)
print(lexicon.segment("compilerword"))
```

Locale is optional runtime presentation state, not a dataset identity. The base language remains `en`, and all of these requests can use the same physical artifact:

```python
neutral = Lexicon("en")
british = Lexicon("en", locale="GB")
american = Lexicon("en", locale="en-US")
```

`locale` accepts the canonical `GB` and `US` values plus their supported aliases. Without a locale, English remains region-neutral. Locale-aware ordering and labels use only regional tags retained from source data. Frequency remains base-language English data, not British or American frequency.

Runtime access is local-only, deterministic, read-only, and never fetches missing entries or mutates the database. `complete()` performs deterministic normalized lexical-key prefix completion and is not a spelling corrector. It requires only the `lexical` capability, returns an exact key first, and ranks remaining full-prefix matches by corpus rank when available or lexical order otherwise. `segment()` and semantic context operations require full authoritative coverage.

The public runtime operations are:

```python
lexicon.word("compiler")
lexicon.contains("compiler")
lexicon.segment("chatgpt")
lexicon.context_domains(text, target=(start, end))
lexicon.supports_domain(text, target=(start, end), domain="computing")
lexicon.entries("compiler")  # rich artifacts only
```

Dictionary membership is authoritative. Frequency rank and count enrich existing lexemes but never create corpus-only words. `Lexicon.word()` reports normalized membership and the attested lowercase, titlecase, and uppercase forms. `uppercase_only` is true only for a known lexeme with uppercase attestation and no lowercase or titlecase attestation.

`Lexicon.segment()` additionally applies surface-case acceptance rules. Therefore, an uppercase-only `GPT` entry does not validate lowercase `gpt`, and `segment("chatgpt")` can report `chat` as known and `gpt` as unknown. Consumers can use the richer `word()` evidence for context-specific policy without weakening segmentation.

Semantic results are explainable `DomainEvidence` values containing score and nearby `ContextCue` records. Context is measured from the target character span: overlapping lexical tokens are excluded, while a target containing no lexical token acts as a virtual boundary and leaves adjacent words eligible at distance 1. These are soft hints, so missing evidence is not negative evidence and positive evidence is not semantic certainty.

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
lexhint word compiler -l en
lexhint word compiler -l en --variant runtime
lexhint segment chatgpt -l en --dataset-version 2026.08.20
lexhint context "The compiler is 8.3.2." -l en --target 16:21
lexhint complete comp -l en --limit 10
lexhint --json complete comp -l en --limit 10
lexhint dictionary word compiler -l en --variant rich
lexhint dictionary status en --variant runtime
```

All artifact-consuming query commands accept `--variant` and `--dataset-version`; `--path` remains an explicit custom-file override. Use `--json` for one JSON document on stdout. Dataset `list`, `info`, and `validate` are local; `available` and `download` access the published catalog.

Dictionary word output has three human-readable detail levels. The default `standard` view shows all senses with compact metadata. Use `compact` for a deliberately short shell view, or `full` for every field retained by the local Lexhint dictionary model:

```bash
lexhint dictionary word love
lexhint dictionary word love --detail compact
lexhint dictionary word love --detail full
lexhint dictionary word love --detail full --hide examples,tags
lexhint dictionary word love --detail compact --show examples
lexhint dictionary word love --pos noun,verb --exclude-pos proper_noun
lexhint --json dictionary word love --pos noun
```

The `--show` and `--hide` options accept repeatable comma-separated fields. Canonical fields are `etymology`, `pronunciations`, `forms`, `tags`, `topics`, `examples`, `synonyms`, and `antonyms`; the `all`, `entry`, `sense`, and `relations` groups are also supported. `--width` controls human output from 40 through 240 columns.

Human CLI output uses ANSI color automatically on interactive terminals. Use `--no-color` or the `NO_COLOR` environment variable to disable it. Color is never emitted for JSON or non-TTY stdout.

Use `--json` for stable, complete machine-readable output. POS selection applies to JSON entries, while `--detail`, `--show`, `--hide`, and `--width` are human-only options. `dictionary status` reports current SQL row counts, capabilities, provenance, size, and build metadata without rebuilding. Use `--path` as an advanced override when inspecting a specific artifact. Rich dictionary lookup reports a controlled capability error for compact runtime artifacts.

## Data and scope

The builder consumes Wiktextract-compatible JSONL, commonly from Kaikki, and FrequencyWords full files for optional corpus enrichment. See [DATA_SOURCES.md](DATA_SOURCES.md) for source and licensing information.

Lexhint does not implement Spokenform integration, dataset publication, URL parsing, speech rendering, or consumer-specific interpretation rules. The separate `buchwandler/lexhint-datasets` repository is outside this project.

## Development

Contributor setup uses an editable installation with development tools:

```bash
git clone https://github.com/buchwandler/lexhint.git
cd lexhint
python -m pip install -e ".[dev]"
pytest -q
ruff check .
mypy lexhint
```
