[![PyPI - Version](https://img.shields.io/pypi/v/lexhint)](https://pypi.org/project/lexhint/)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/lexhint)
![PyPI - Downloads](https://img.shields.io/pypi/dm/lexhint)
[![codecov](https://codecov.io/gh/buchwandler/lexhint/graph/badge.svg?token=53idb7ZCY1)](https://codecov.io/gh/buchwandler/lexhint)

# lexhint

`lexhint` provides compact lexical and dictionary-derived semantic evidence for
text-normalization and speech frontends such as `spokenform`.

It does **not** verbalize text itself. Its three related capabilities are:

1. determine whether text is a common word and split compact identifiers/domain labels;
2. provide lightweight grouped dictionary lookup backed by curated Wiktionary data;
3. derive semantic context evidence from dictionary topics for a candidate interpretation.

There are no hand-maintained per-language context JSON files.

## Quick start

Install for development:

```bash
python -m pip install -e ".[dev]"
```

Prepare the default English word list and try the CLI:

```bash
lexhint setup
lexhint word house
lexhint segment chatgpt
```

English is the CLI default. Use an explicit language when needed:

```bash
lexhint setup de
lexhint word de Haus
# or: LEXHINT_LANGUAGE=de lexhint word Haus
```

Human-readable output is the default; add `--json` to any command for scripts.
The runtime itself has no third-party Python dependencies.

Dictionary operations fetch only the requested Kaikki word page by default and cache
curated rich dictionary entries locally:

```bash
lexhint dictionary word compiler
lexhint dictionary fetch scale house compiler
```

Use `--offline` to require cached data. The full Kaikki source remains available for
maintainers and advanced offline users:

```bash
lexhint dictionary build en
lexhint setup en --dictionary
```

The bulk source is large and is streamed rather than downloaded to a temporary copy.

## Layout

The project deliberately uses a flat source layout:

```text
.
├── lexhint/
├── tests/
├── tools/
└── pyproject.toml
```

There is no `src/` directory.

## Dynamic versioning

Versions come from Git tags through `setuptools-scm`:

```bash
git init
git add .
git commit -m "Initial lexhint MVP"
git tag v0.1.0
python -m build
```

The bootstrap ZIP configures `0.1.0` as the `setuptools-scm` fallback version because Git
metadata is not part of a normal ZIP archive. Installed runtime version lookup uses
`importlib.metadata`, so no generated version module is kept in the source tree.

# 1. Dictionary lexical data

All runtime lexical operations use the installed SQLite dictionary dataset. Dictionary membership and corpus commonness are separate: a known word may have no corpus statistic.

```bash
lexhint setup
lexhint word compiler
lexhint segment compilerword
```

The runtime artifact is:

```text
~/.cache/lexhint/dictionaries/<language>.sqlite3
```

Python:

```python
from lexhint import Dictionary

dictionary = Dictionary("en")
info = dictionary.word_info("compiler")
assert info.known
print(info.frequency_rank, info.frequency_count)
print(dictionary.segment("compilerword"))
```

Segmentation requires a full-coverage dictionary dataset. `LexicalSegment.known` reports dictionary membership; frequency rank is optional corpus evidence. URL syntax remains the caller's responsibility.

# 2. Dictionary-derived context

Instead of maintaining a file such as `en.json`, build a curated rich dictionary index from
Wiktextract/Kaikki JSONL.

The Kaikki raw English-edition extraction contains many languages, so the builder checks
`lang_code` and can produce indexes for `en`, `de`, `fr`, and other languages from the
same source when those entries are present.

The dictionary dataset can be enriched at build time with a pinned FrequencyWords full file. The corpus source provides rank and count evidence only; it does not add lexemes.

```bash
lexhint dictionary build en ~/Downloads/raw-wiktextract-data.jsonl.gz \
    --frequency-source ~/Downloads/en_full.txt
```

The builder reads sources line-by-line and stores grouped dictionary entries containing definitions, usage labels, examples, forms, IPA pronunciations, basic relations, semantic topics, canonical lexemes, case flags, and optional corpus statistics. The resulting database defaults to:

```text
~/.cache/lexhint/dictionaries/en.sqlite3
```

Schema-6 indexes store the rich hierarchy, lexeme membership table, corpus provenance, and coverage metadata. Partial indexes support exact lazy lookup but are not sufficient for reliable segmentation. Full local indexes record source hashes; composite snapshot identity covers both dictionary and frequency inputs.
index metadata, while `Dictionary.from_path(path, language="en")` asserts it.

Each entry contains:

```text
display spelling
part of speech
optional etymology
forms and pronunciations
ordered senses
```

Each sense can contain:

```text
glosses
topics
usage/grammar tags
examples
synonyms and antonyms
```

It is deliberately not a full Wiktionary mirror. Categories, translations, templates, and
other source-specific maintenance metadata are not part of the curated public model.

## Dictionary API

```python
from lexhint import Dictionary

dictionary = Dictionary("en", fetch_missing=True)

print(dictionary.lookup("scale"))  # fetches once, then works offline
print(dictionary.senses("scale"))  # convenience flattening of lookup()
print(dictionary.topics("compiler"))
```

`Dictionary.from_path(path)` infers the language from index metadata. Supply
`language="en"` when the caller wants the index language asserted explicitly. Use
`refresh=True` on `lookup()`, `senses()`, or the context methods to refresh a cached word when
network access is enabled.

The default `Dictionary("en")` is local-only. Use `fetch_missing=True` only when the
application explicitly permits network access.

No topic score is negative evidence. It means that no positive evidence was found in
the available dictionary coverage and annotations; a missing word, a partial cache, or
sparse upstream topic labels can all produce no score. Use a local full snapshot and
`offline=True` for deterministic benchmark or production runs.

Wiktextract provides `topics` per sense when Wiktionary supplies that semantic metadata.
A word can therefore have several senses with different topics instead of being globally
assigned to one manually maintained domain.

## Candidate-aware context evidence

`spokenform` already knows the interpretation it wants to test. `lexhint` only answers
whether nearby dictionary senses support its semantic topic.

```python
from lexhint import Dictionary

lex = Dictionary("en")

text = "The scale is Am."
start = text.index("Am")

support = lex.supports(
    text,
    target=(start, start + len("Am")),
    topic="music",
)

assert support is not None
print(support.cues)  # includes "scale" when its dictionary sense has topic=music
```

Likewise for software versions:

```python
text = "The compiler is 8.3.2."
start = text.index("8.3.2")

support = lex.supports(
    text,
    target=(start, start + len("8.3.2")),
    topic="computing",
)
```

The target token itself is deliberately excluded from context evidence. A candidate
cannot validate its own interpretation.

`topic_scores()` returns `TopicEvidence` values. Each value includes structured
`ContextCue` records with the cue text, source span, token distance, and decay weight.
Use `window`, `decay`, and `limit` to control the diagnostic search; `supports()` also
accepts a score `threshold`. An absent score is not negative evidence.

For diagnostics, inspect all nearby dictionary topics:

```python
for score in lex.topic_scores(text, target=(start, start + len("8.3.2"))):
    print(score.topic, score.score)
    print([(cue.text, cue.start, cue.end, cue.distance, cue.weight) for cue in score.cues])
```

CLI:

```bash
lexhint dictionary word en compiler
lexhint dictionary fetch scale house compiler
lexhint --offline dictionary word en compiler
lexhint context en music "The scale is Am." --target Am
lexhint --offline context en computing "The compiler is 8.3.2." --target 8.3.2
```

# Integration boundary with spokenform

The intended flow is:

```text
Wiktextract/Kaikki ─┐
                    ├─> schema-6 SQLite dictionary ──> lexhint ──> spokenform
FrequencyWords ─────┘       (build-time enrichment)

Examples:

```text
chatgpt.com
    lexhint: chat is lexical, gpt is an unknown run
    spokenform: chat g p t dot com

The scale is Am.
    lexhint: nearby "scale" has a music sense
    spokenform: Am -> A minor

The compiler is 8.3.2.
    lexhint: nearby "compiler" has a computing sense
    spokenform: 8.3.2 -> version eight dot three dot two
```

`lexhint` does not contain rules for `Am -> A minor`, version pronunciation, URL symbol
names, or other speech policy. Those remain in the speech/text-normalization layer.

# Vendoring data for an offline wheel

Dictionary indexes:

```bash
python tools/vendor_dictionary.py en
```

Review `DATA_SOURCES.md` before redistributing external dictionary or frequency data. Generated dataset files have data-license obligations independent of the Apache-2.0-licensed Python code.

# Tests

```bash
python -m pytest
python -m ruff check .
python -m mypy lexhint
```
