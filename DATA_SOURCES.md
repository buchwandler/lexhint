# Data sources

`lexhint` code is Apache-2.0 licensed. This source archive does not bundle the external
frequency lists or Wiktionary-derived dictionary data described below.

## FrequencyWords

`lexhint fetch <language>` downloads a 50,000-word frequency list from:

- FrequencyWords by hermitdave
- https://github.com/hermitdave/FrequencyWords
- source corpus: OpenSubtitles 2018
- upstream repository states: MIT for code, CC BY-SA 4.0 for generated content

The downloaded list is normalized locally into a gzip file with one word per line.
Its line number is the frequency rank.

## Wiktionary / Wiktextract / Kaikki

`lexhint dictionary word` and `lexhint dictionary fetch` may lazily download one
Kaikki single-word raw JSONL page at a time. Only the requested page is transferred;
lexhint filters its requested `lang_code` and stores curated rich dictionary entries in a
local schema-v5 SQLite partial cache. Successful empty and not-found lookups are recorded
so they are not repeatedly requested. The `--offline` option disables all network access.

`lexhint dictionary build` reads Wiktextract-compatible JSONL for complete offline
coverage. The recommended source is the pre-extracted data published by Kaikki:

- https://kaikki.org/dictionary/rawdata.html
- current raw English Wiktextract download URL used in the MVP:
  https://kaikki.org/dictionary/raw-wiktextract-data.jsonl.gz
- Wiktextract project: https://github.com/tatuylonen/wiktextract

Both lazy and bulk paths use the same curated rich extraction policy. The builder streams
the source, keeps entries whose `lang_code` matches the requested language, and preserves
source entry and sense order. Stored fields are:

- normalized word key and display spelling
- part of speech and compact etymology text
- forms and pronunciations
- sense glosses and explicit topics
- usage/grammar tags
- examples with optional translations
- basic synonyms and antonyms

Context scoring uses only the normalized topic index, not the rich JSON payloads. The
FrequencyWords lexicon is a separate resource and is not used as a dictionary allowlist.
Categories, translations beyond examples, templates, raw source metadata, and maintenance
fields are not part of the curated public model.

Wiktionary entry text is dual-licensed under CC BY-SA 4.0 and GFDL. If you vendor
or redistribute a generated SQLite dictionary, review and comply with the applicable
Wiktionary, Wiktextract/Kaikki, and source attribution/license requirements.

`lexhint` deliberately keeps generated dictionary databases out of the source ZIP so
that code licensing and data licensing remain separate.
