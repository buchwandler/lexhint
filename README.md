# lexhint

`lexhint` provides compact lexical and dictionary-derived semantic evidence for
text-normalization and speech frontends such as `spokenform`.

It does **not** verbalize text itself. Its two jobs are:

1. determine whether text is a common word and split compact identifiers/domain labels;
2. extract semantic topics from a real dictionary and use nearby dictionary senses as
   context evidence for a candidate interpretation.

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
compact dictionary senses locally:

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
```

Override the complete cache root with `LEXHINT_CACHE_DIR`.

Python:

```python
from lexhint import Lexicon

lex = Lexicon("en")

assert lex.contains("chat")
print(lex.rank("chat"))
print(lex.segment("chatgpt"))
```

Expected segmentation shape:

```python
(
    Segment(text="chat", known=True, rank=...),
    Segment(text="gpt", known=False, rank=None),
)
```

A speech layer can therefore keep `chat` lexical and spell the unknown `gpt` run.

CLI:

```bash
lexhint word chat
lexhint segment chatgpt
```

# 2. Dictionary-derived context

Instead of maintaining a file such as `en.json`, build a compact dictionary index from
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

That source is very large. The builder reads it line-by-line and stores compact
dictionary senses containing glosses and explicit semantic topics. Context scoring uses only
the explicit topics. Dictionary vocabulary is not restricted to the FrequencyWords common-word
list; technical semantic cues such as "compiler" can therefore be retained. The resulting
database defaults to:

```text
~/.cache/lexhint/dictionaries/en.sqlite3
```

The schema v4 index stores compact sense rows plus partial-cache coverage metadata.
Each row contains:

```text
word
display spelling
part of speech
glosses
topics
```

It is deliberately not a full Wiktionary mirror. A sense is retained when it has a
dictionary gloss or an explicit entry-level or sense-level Wiktextract topic.

## Dictionary API

```python
from lexhint import Dictionary

dictionary = Dictionary("en", fetch_missing=True)

print(dictionary.senses("scale"))  # fetches once, then works offline
print(dictionary.topics("compiler"))
```

The default `Dictionary("en")` is local-only. Use `fetch_missing=True` only when the
application explicitly permits network access.

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

For diagnostics, inspect all nearby dictionary topics:

```python
for score in lex.topic_scores(text, target=(start, start + len("8.3.2"))):
    print(score)
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
