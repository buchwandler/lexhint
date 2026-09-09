[![PyPI - Version](https://img.shields.io/pypi/v/lexhint)](https://pypi.org/project/lexhint/)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/lexhint)
![PyPI - Downloads](https://img.shields.io/pypi/dm/lexhint)
[![codecov](https://codecov.io/gh/buchwandler/lexhint/graph/badge.svg?token=53idb7ZCY1)](https://codecov.io/gh/buchwandler/lexhint)

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

Dataset source and capability are independent selectors. `language` is always the lexical target language. `source_variant=native` reads the matching Wiktionary edition, while `source_variant=english` reads the English Wiktionary edition and keeps English source metadata. English is the default when available; native is the fallback when no English publication exists. The short aliases `-n` and `-e` select those same canonical values.

```bash
lexhint dataset download de -n
lexhint dataset download de -e
lexhint dictionary search -l de -e Haus
lexhint dataset list --language de -e
```

Both source variants can be installed simultaneously. Their canonical paths include language, source variant, capability variant, schema, and version. Historical source-unqualified catalog entries, release assets, and sidecars continue to mean `native`.

When a command needs one installed artifact and no source variant is given, Lexhint selects English if a matching English-source artifact is installed; otherwise it selects native. If only one source is installed, that source is selected automatically. `--variant` and `--dataset-version` narrow the candidate set but do not change this source-preference rule. Inventory commands such as `dataset list`, `available`, `check`, `update`, and `validate` continue to expose all matching source variants unless filtered. `dataset remove` selects the only matching source, but requires `-e` or `-n` when both sources match.

The short selectors are aliases for the long forms: `-e` is `--source-variant english`, and `-n` is `--source-variant native`.
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
The managed store is keyed by lexical target language, source variant, capability variant, exact SQLite schema, and dataset version. New artifacts use `datasets/<language>/<source_variant>/<variant>/s<schema>/<version>/lexhint.sqlite3`; existing native artifacts in the historical layout remain readable. A local-build alternative is available with `lexhint dictionary build`; pass its output with `--path` when querying.

For a small local artifact without FrequencyWords enrichment, build from the repository fixture with `lexhint dictionary build en --source tests/fixtures/kaikki-mini.jsonl --output /tmp/lexhint-en.sqlite3 --no-frequency` and pass `--path /tmp/lexhint-en.sqlite3` to the query commands.

## 1. Common-word lexicon

Open the highest-capability installed artifact with `Lexicon`, or select a variant/version explicitly:

```python
from lexhint import Lexicon

lexicon = Lexicon("en")  # highest installed compatible variant
runtime = Lexicon("en", variant="runtime")
english_metadata = Lexicon("de", source_variant="english")
pinned = Lexicon("en", variant="runtime", dataset_version="2026.08.20")
info = lexicon.word("compiler")
print(info.known, info.frequency_rank, info.has_lowercase, info.has_titlecase, info.has_uppercase)
print(lexicon.segment("compilerword"))
```

Locale is optional runtime presentation state, not a dataset identity. `language` is the physical lexical language, while `locale` is a regional pronunciation and presentation preference. A full locale tag can supply its base language in CLI commands:

```python
neutral = Lexicon("en")
american = Lexicon("en", locale="en-US")
british = Lexicon("en", locale="en-GB")
brazilian = Lexicon("pt", locale="pt-BR")
portuguese = Lexicon("pt", locale="pt-PT")
```

`locale` accepts canonical BCP-47-style tags such as `en-US`, `en-GB`, `pt-BR`, and `pt-PT`, plus supported short and underscore aliases. Locale-aware ordering and labels use only regional tags retained from the selected source artifact. Frequency remains base-language data, not regional frequency.

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

Advanced query controls are available for bounded semantic and fuzzy searches:

```bash
lexhint context "The compiler is 8.3.2." --target 16:21 --window 8 --decay 0.8 --limit 5
lexhint suggest compilar -l en --variant rich --max-distance 2
```

`context --window` limits lexical cue distance, `--decay` sets per-distance evidence decay, and `--limit` caps semantic domains. `suggest --max-distance` bounds edit distance; its `--limit` caps returned candidates. Dictionary search accepts comma-separated `--fields` and `--match all` or `any`. Relation names are accepted through repeatable, comma-separated `--relation` options.

All artifact-consuming query commands accept `--source-variant` (or the `-e` / `-n` aliases), `--variant`, and `--dataset-version`; `--path` remains an explicit custom-file override and cannot be combined with selectors. English is preferred when source is omitted and native is used only when no English source exists. Use `--json` for one JSON document on stdout. Dataset `list`, `info`, and `validate` are local; `available` and `download` read the static catalog. Exact schema equality is required, and historical releases remain usable through catalog entries or the compatibility Releases API fallback.

Dataset lifecycle commands accept `--version` and the additive `--dataset-version` alias where an exact version is supported. Human output uses the canonical identity `<language>/<source_variant>/<variant>` so coexisting source editions remain distinguishable:

```bash
lexhint dataset info en --variant runtime
lexhint dataset validate en
lexhint dataset remove en --variant runtime -e
```

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

Return only pronunciation data, grouped by part of speech. IPA is rendered with canonical square brackets, and focused pronunciation lookup includes all display-case variants for the normalized word:

```bash
lexhint dictionary pronunciation love
```

The human result uses square-bracket IPA, for example `[ˈlʌv]`. Equivalent slash and square-bracket source forms with identical tags are shown once. When display-case variants share a normalized lexical key, the requested spelling is shown first and each variant keeps its own pronunciation groups.

Filter by an exact retained source region or accent tag:

```bash
lexhint dictionary pronunciation love --region Canada
```

Select pronunciations through a user-facing locale profile:

```bash
lexhint dictionary pronunciation love --locale en-US
lexhint dictionary pronunciation leite --locale pt-BR
lexhint dictionary pronunciation leite --locale pt-PT
```

`--region` performs exact normalized matching against a retained source pronunciation tag. It is useful for source-specific accents such as `Caipira`, `Paulistana`, `Canada`, or `General-American`, but it is not the normal language/region selector.

Filter pronunciation by part of speech with repeatable, comma-separated `--pos` values. Locale selection and source selection are independent: locale chooses regional evidence inside the selected artifact, while `--source-variant` chooses the Wiktionary edition:

```bash
lexhint dictionary pronunciation live --locale en-US --pos verb
lexhint dictionary pronunciation leite --locale pt-BR --source-variant english
```

A locale never switches the Wiktionary source variant.
`--locale` is the normal pronunciation preference. It selects matching retained evidence and otherwise falls back to untagged pronunciations for that word and part-of-speech group. If multiple distinct untagged pronunciations are the only fallback, the CLI reports that the requested regional evidence was not available. A locale does not synthesize missing pronunciations or silently switch Wiktionary editions.

Use `--include-neutral` to include untagged pronunciations alongside matching region or locale pronunciations. Without a filter, all retained pronunciations are already returned, so `--include-neutral` has no additional effect. Use global `--json` for machine-readable results.

The same query is available through the Python API:

```python
from lexhint import Lexicon

american = Lexicon("en", locale="en-US").pronunciations("love")
canadian = Lexicon("en").pronunciations("love", region="Canada")
```

For a complete local pronunciation export, use the lazy bulk iterator on a dictionary-capable artifact:

```python
from lexhint import Lexicon

lexicon = Lexicon(
    "en",
    variant="dictionary",
    dataset_version="2026.08.20",
    locale="en-US",
)
for entry in lexicon.iter_pronunciations(include_neutral=True):
    print(entry.key, entry.groups)
```

The dataset identity remains the base language (`en`); a locale such as `en-US` is a normalized presentation and filtering view over the same artifact. `iter_pronunciations()` requires the `dictionary` capability, is local-only and deterministic, and does not download missing data. It streams normalized keys in stable order and retains display-case variants, source tags, and normalized POS groups inside each entry. Tags and POS are source evidence for consumers, not pronunciation-choice guarantees.

## Dictionary schema 10 contract

Schema 10 dictionary entries expose a versioned deterministic `sense_id` in JSON and through `Lexicon.sense_by_id()`. The ID is Lexhint-owned and stable across equivalent builds, not a permanent Wiktionary ID. Raw upstream `senseid` and Wikidata values, when available, appear separately as namespaced source provenance. Entry-level synonyms, antonyms, hypernyms, hyponyms, and related terms are headword relations; sense-level synonyms and antonyms remain attached to their exact senses.

Use the incoming relation view when a target headword is the subject of the lookup:

```bash
lexhint dictionary relations love --incoming --variant dictionary
```

Schema 10 artifacts are rebuilt from raw source rather than migrated. The `dictionary` variant contains full dictionary content without search indexes. The `rich` variant adds the larger fuzzy and definition-search indexes.
Use `--json` for stable, complete machine-readable output. POS selection applies to JSON entries, while `--detail`, `--show`, `--hide`, and `--width` are human-only options. `dictionary status` reports current SQL row counts, capabilities, provenance, size, and build metadata without rebuilding. Use `--path` as an advanced override when inspecting a specific artifact. Rich dictionary lookup reports a controlled capability error for compact runtime artifacts.

## Environment variables

The public environment contract includes:

- `LEXHINT_LANGUAGE` sets the default base language when `-l/--language` is omitted.
- `LEXHINT_DATA_DIR` overrides managed dataset storage.
- `LEXHINT_CACHE_DIR` overrides the catalog and source cache.
- `NO_COLOR` disables ANSI color output.

Advanced users may set `LEXHINT_GITHUB_TOKEN` to reduce GitHub API rate-limit failures. `LEXHINT_DATASET_CATALOG_URL` is an internal/testing override and is not a stable deployment contract. `XDG_DATA_HOME` and `XDG_CACHE_HOME` provide platform-level directory defaults when Lexhint-specific variables are unset.

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
