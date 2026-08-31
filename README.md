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

`lexhint dataset download` and `lexhint dataset update` are the operations that download dataset assets. They read the `lexhint-datasets` catalog, cache and conditionally refresh that catalog, then download selected assets from immutable GitHub Release URLs. The catalog is an index, not a replacement for release manifests: detailed provenance remains in each release's `datasets-v2.json`. `Lexicon`, query commands, and local dataset inventory do not silently contact GitHub.
The download default is the `runtime` variant (`lexical,semantic`). Optional variants are:

- `lexical` for membership, frequency, and segmentation;
- `runtime` for lexical and semantic context evidence;
- `dictionary` for entries, senses, topics, and rich dictionary rendering without search indexes;
- `rich` for everything in `dictionary`, plus fuzzy suggestions and indexed definition/reverse search.

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

View all compatible catalog downloads, check installed datasets, and update them:

```bash
lexhint dataset available
lexhint dataset check
lexhint dataset check en --variant runtime
lexhint dataset update
lexhint dataset update en --variant runtime
```

The catalog is cached under `LEXHINT_CACHE_DIR` (or the platform cache directory) and refreshed conditionally when dataset commands access the network. A valid cached catalog is used when refreshing fails; `--offline dataset available` and `--offline dataset check` read that cache without making a request. `dataset update` processes every installed language and variant by default, or the selected filters, and removes superseded versions only after the replacement has been verified. It does not install datasets that are not already present.
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

Runtime access is local-only, deterministic, read-only, and never fetches missing entries or mutates the database. `complete()` performs deterministic normalized lexical-key prefix completion and is not a spelling corrector. It requires only the `lexical` capability, returns an exact key first, and ranks remaining full-prefix matches by corpus rank when available or lexical order otherwise. `suggest()` is the separate bounded fuzzy-spelling API and requires `search`; `match_headwords()` provides glob/regex matching; `search_definitions()` provides indexed dictionary-text search and requires `dictionary` plus `search`. Search results are bounded by the artifact's available coverage. `segment()` and semantic context operations require full authoritative coverage.

The public runtime operations are:

```python
lexicon.word("compiler")
lexicon.contains("compiler")
lexicon.segment("chatgpt")
lexicon.context_domains(text, target=(start, end))
lexicon.supports_domain(text, target=(start, end), domain="computing")
rich = Lexicon("en", variant="rich")
rich.entries("compiler")
rich.suggest("complier", limit=20)
rich.match_headwords("comp*", syntax="glob")
rich.search_definitions("computer program", fields=("glosses",), match="all")
```

Dictionary membership is authoritative. Frequency rank and count enrich existing lexemes but never create corpus-only words. `Lexicon.word()` reports normalized membership and the attested lowercase, titlecase, and uppercase forms. `uppercase_only` is true only for a known lexeme with uppercase attestation and no lowercase or titlecase attestation.

`Lexicon.segment()` additionally applies surface-case acceptance rules. Therefore, an uppercase-only `GPT` entry does not validate lowercase `gpt`, and `segment("chatgpt")` can report `chat` as known and `gpt` as unknown. Consumers can use the richer `word()` evidence for context-specific policy without weakening segmentation.

Semantic results are explainable `DomainEvidence` values containing score and nearby `ContextCue` records. Context is measured from the target character span: overlapping lexical tokens are excluded, while a target containing no lexical token acts as a virtual boundary and leaves adjacent words eligible at distance 1. These are soft hints, so missing evidence is not negative evidence and positive evidence is not semantic certainty.

## Build an artifact

The default build creates a full `lexical,semantic,dictionary,search` artifact and automatically acquires the pinned full FrequencyWords source:

```bash
lexhint dictionary build en
```

Use a local or remote dictionary source and explicit build policies when needed:

```bash
lexhint dictionary build en --source ./raw-wiktextract-data.jsonl.gz
lexhint dictionary build en --capabilities lexical,semantic --no-frequency
lexhint dictionary build en --capabilities lexical,search --no-frequency
lexhint dictionary build en --profile runtime
lexhint dictionary build en --frequency-source ./en_full.txt
lexhint dictionary build en --refresh-frequency
lexhint --offline dictionary build en --source ./raw-wiktextract-data.jsonl.gz
```

Capabilities are canonicalized in the order `lexical,semantic,dictionary,search`. `semantic`, `dictionary`, and `search` require `lexical`. Dictionary-text search additionally requires `dictionary`. Profiles are shortcuts: `runtime` means `lexical,semantic`, `dictionary` means `lexical,semantic,dictionary` without search indexes, and `rich` means `lexical,semantic,dictionary,search`.

`complete()` is prefix completion only; it does not correct spelling. Use `suggest()` for fuzzy spelling candidates, `match_headwords()` for glob/regex lexical-key matching, and `search_definitions()` for indexed dictionary sense search.

Frequency enrichment is independent of capabilities. Use `--no-frequency` for a valid lexical artifact without corpus data. Automatic sources are cached under `~/.cache/lexhint/sources/frequencywords/<revision>/`, or an equivalent XDG/`LEXHINT_CACHE_DIR` location. Builds record source URLs, revisions, hashes, schema, capabilities, and builder metadata. Build configuration and progress are written to stderr, while the final result, including JSON, is written to stdout.

## CLI queries

The default download installs the `runtime` variant. Install the `rich` variant before using search-capable commands such as `suggest`, `headwords`, or `dictionary search`:

```bash
lexhint dataset download en --variant rich
```

```bash
lexhint word compiler -l en
lexhint word compiler -l en --variant runtime
lexhint segment chatgpt -l en --dataset-version 2026.08.20
lexhint context "The compiler is 8.3.2." -l en --target 16:21
lexhint complete comp -l en --limit 10
lexhint --json complete comp -l en --limit 10
lexhint suggest compilar -l en --variant rich --limit 10
lexhint headwords 'comp*' -l en --variant rich --syntax glob
lexhint dictionary search "large feline" -l en --variant rich --fields glosses --match all
lexhint --json dictionary search "large feline" -l en --variant rich
lexhint dictionary word compiler -l en --variant rich
lexhint dictionary status en --variant runtime
```

All artifact-consuming query commands accept `--variant` and `--dataset-version`; `--path` remains an explicit custom-file override. Use `--json` for one JSON document on stdout. Dataset `list`, `info`, and `validate` are local; `available` and `download` read the static catalog. Exact schema equality is required, and historical releases remain usable through catalog entries or the compatibility Releases API fallback.

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

## Pronunciation lookup

Return only pronunciation data, grouped by part of speech:

```bash
lexhint dictionary pronunciation love
```

Filter by an exact retained source region or accent tag:

```bash
lexhint dictionary pronunciation love --region Canada
```

Select pronunciations through a locale profile:

```bash
lexhint dictionary pronunciation love --locale en_US
lexhint dictionary pronunciation love --locale en_GB
lexhint dictionary pronunciation love --locale en_CA
```

`--region` performs exact normalized source-tag matching. `--locale` maps a locale to its configured set of retained pronunciation tags. Use global `--json` for machine-readable results.

The same query is available through the Python API:

```python
from lexhint import Lexicon

american = Lexicon("en", locale="en_US").pronunciations("love")
canadian = Lexicon("en").pronunciations("love", region="Canada")
```

## Dictionary schema 10 contract

Schema 10 dictionary entries expose a versioned deterministic `sense_id` in JSON and through `Lexicon.sense_by_id()`. The ID is Lexhint-owned and stable across equivalent builds, not a permanent Wiktionary ID. Raw upstream `senseid` and Wikidata values, when available, appear separately as namespaced source provenance. Entry-level synonyms, antonyms, hypernyms, hyponyms, and related terms are headword relations; sense-level synonyms and antonyms remain attached to their exact senses.

Use the incoming relation view when a target headword is the subject of the lookup:

```bash
lexhint dictionary relations love --incoming --variant dictionary
```

Schema 10 artifacts are rebuilt from raw source rather than migrated. The `dictionary` variant contains full dictionary content without search indexes. The `rich` variant adds the larger fuzzy and definition-search indexes.
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
