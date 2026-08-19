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
lexhint filters its requested `lang_code` and stores compact dictionary senses in a
local schema-v4 SQLite partial cache. Successful empty and not-found lookups are recorded
so they are not repeatedly requested. The `--offline` option disables all network access.

`lexhint dictionary build` reads Wiktextract-compatible JSONL for complete offline
coverage. The recommended source is the pre-extracted data published by Kaikki:

- https://kaikki.org/dictionary/rawdata.html
- current raw English Wiktextract download URL used in the MVP:
  https://kaikki.org/dictionary/raw-wiktextract-data.jsonl.gz
- Wiktextract project: https://github.com/tatuylonen/wiktextract

Both lazy and bulk paths use the same compact sense extraction policy. The builder streams
the source, keeps entries whose `lang_code` matches the requested language, and stores a
compact sense when it has a dictionary gloss or an explicit semantic topic. Context scoring
uses only explicit semantic topics. The FrequencyWords lexicon is a separate resource and
is not used as a dictionary allowlist. Stored fields are:

- normalized word key
- display spelling
- part of speech
- glosses
- explicit topics

Categories, tags, examples, translations, forms, and other raw Wiktionary metadata are not
stored.

Wiktionary entry text is dual-licensed under CC BY-SA 4.0 and GFDL. If you vendor
or redistribute a generated SQLite dictionary, review and comply with the applicable
Wiktionary, Wiktextract/Kaikki, and source attribution/license requirements.

`lexhint` deliberately keeps generated dictionary databases out of the source ZIP so
that code licensing and data licensing remain separate.
