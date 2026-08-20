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

# 1. Common-word lexicon

Fetch a FrequencyWords top-50k list:

```bash
lexhint fetch en
lexhint fetch de fr es it pt cs
```

Default cache:

```text
~/.cache/lexhint/words/<language>.txt.gz
~/.cache/lexhint/words/<language>.metadata.json
```

Override the complete cache root with `LEXHINT_CACHE_DIR`.

Word-list downloads use a pinned FrequencyWords revision. The metadata sidecar records
the source revision, normalized content SHA-256, language, and word count, so a cache
can be checked for provenance and corruption before it is reused. Use `--force` when an
explicit refresh is wanted.

Python:

```python
from lexhint import LexicalSegment, Lexicon

lex = Lexicon("en")

assert lex.contains("chat")
print(lex.rank("chat"))
print(lex.segment("chatgpt"))
```

Word lists load lazily. Pass `path` to use a specific gzip list, `auto_fetch=True` to
opt into downloading a missing list, or use `Lexicon.from_words(words)` for an
in-memory lexicon in tests and embedded applications.

Expected segmentation shape:

```python
(
    LexicalSegment(text="chat", in_lexicon=True, frequency_rank=...),
    LexicalSegment(text="gpt", in_lexicon=False, frequency_rank=None),
)
```

`in_lexicon` is lexical-resource evidence only. It is not a pronunciation or
interpretation decision. `Lexicon.segment()` accepts one compact identifier or domain
label; the caller owns URL schemes, dots, paths, ports, and other URL syntax.

CLI:

```bash
lexhint word chat
lexhint segment chatgpt
```

# 2. Dictionary-derived context

Instead of maintaining a file such as `en.json`, build a curated rich dictionary index from
Wiktextract/Kaikki JSONL.

The Kaikki raw English-edition extraction contains many languages, so the builder checks
`lang_code` and can produce indexes for `en`, `de`, `fr`, and other languages from the
same source when those entries are present.

The common-word lexicon and semantic dictionary are independent resources. Dictionary
building does not require a FrequencyWords list. To build from a downloaded Kaikki file:

```bash
lexhint dictionary build en ~/Downloads/raw-wiktextract-data.jsonl.gz
```

The lazy word path avoids the multi-gigabyte download entirely. For complete local
coverage, use the built-in official Kaikki source directly:

```bash
lexhint dictionary build en
```

That source is very large. The builder reads it line-by-line and stores grouped dictionary
entries containing definitions, usage labels, examples, forms, pronunciations, basic relations,
and explicit semantic topics. Context scoring uses only the topic index. Dictionary vocabulary
is not restricted to the FrequencyWords common-word list; technical semantic cues such as
"compiler" can therefore be retained. The resulting database defaults to:

```text
~/.cache/lexhint/dictionaries/en.sqlite3
```

The schema v5 index stores ordered entries and senses, compact JSON lexical payloads, an indexed
topic table, and partial-cache coverage metadata. Partial indexes are live, network-opt-in
caches. Full indexes built from a local source are reproducible snapshots identified by their
source SHA-256; a full index built from a remote URL records that it is live-full unless the
caller supplies a separately pinned source. `Dictionary.from_path(path)` reads the language from
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
    print([
        (cue.text, cue.start, cue.end, cue.distance, cue.weight)
        for cue in score.cues
    ])
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
FrequencyWords ──> lexical evidence ─┐
                                     ├─> lexhint ──> evidence ──> spokenform
Wiktionary ──────> sense/topic data ─┘
```

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

Word lists:

```bash
python tools/vendor_wordlists.py en de
```

Dictionary indexes:

```bash
python tools/vendor_dictionary.py en
```

Review `DATA_SOURCES.md` before redistributing external data. Generated dictionary and
word-list files have data-license obligations independent of the Apache-2.0-licensed Python code.

# Tests

```bash
python -m pytest
python -m ruff check .
python -m mypy lexhint
```
