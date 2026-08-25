# Data sources

Lexhint code is Apache-2.0 licensed. External dictionary and corpus data are not bundled by this source archive and may carry separate attribution and redistribution requirements.

## Artifact dimensions

Published artifacts are selected by four independent values:

- `language`: supported physical/base dictionary language such as `en`;
- `locale`: optional runtime preference such as `GB` or `US`, never a separate artifact;
- `variant`: capability profile, one of `lexical`, `runtime`, or `rich`;
- `schema_version`: exact SQLite compatibility key, currently `10`;
- `dataset_version`: published data snapshot.

Lexhint requires exact schema equality. A schema-10 client skips releases for other schema families and never opens an incompatible installed database. Schema 9 artifacts must be rebuilt from raw source. English locale preferences use the same base-language frequency source, because no regional frequency corpus is supplied here.

## FrequencyWords

Default dictionary builds use the pinned full FrequencyWords file for the selected language:

- Provider: [FrequencyWords](https://github.com/hermitdave/FrequencyWords)
- Corpus: OpenSubtitles 2018
- Variant: `<language>_full.txt`
- Revision: the pinned `FREQUENCYWORDS_REVISION` in `lexhint/frequency.py`
- Resolved URL: `https://raw.githubusercontent.com/hermitdave/FrequencyWords/<revision>/content/2018/<language>/<language>_full.txt`

The builder caches the downloaded file by provider, revision, language, and full-file variant. It records the resolved URL and SHA-256 in the SQLite metadata. Frequency rows enrich dictionary-derived lexemes only. They never act as a dictionary allowlist.

Use `--no-frequency` to opt out or `--frequency-source` to provide a reproducible local/custom source. Offline builds may use a cached automatic source or an explicit local source.

## Wiktionary, Wiktextract, and Kaikki

Dictionary builds consume Wiktextract-compatible JSONL, such as the bulk source published by [Kaikki](https://kaikki.org/dictionary/rawdata.html):

```text
https://kaikki.org/dictionary/raw-wiktextract-data.jsonl.gz
```

The builder filters entries by requested `lang_code`, preserves curated lexical and rich fields, and records dictionary source identity and hashes when available. Semantic-domain rows are a deterministic build-time projection of source topic metadata and retain source-topic provenance.

Runtime Lexicon operations do not fetch Kaikki pages, create missing records, or mutate caches. Exact online source tooling is not part of ordinary runtime lookup. Old partial-cache artifacts are incompatible and must be rebuilt.

Wiktionary-derived text is dual-licensed under CC BY-SA 4.0 and GFDL. Wiktextract, Kaikki, FrequencyWords, and the OpenSubtitles corpus have their own terms. Review upstream licenses before vendoring or redistributing generated SQLite artifacts.

## Schema 10 dictionary identity and retained relations

Schema 10 artifacts are rebuilt from raw Wiktextract-compatible JSONL. Kaikki webpage `sense.id` values belong to Kaikki's postprocessed website representation, are absent from the raw bulk source, and are not used by Lexhint. When available, raw `senseid` and Wikidata values are retained as explicitly namespaced provenance.

Each retained sense also receives a versioned Lexhint-owned deterministic `sense_id`. It is stable across equivalent builds using the same identity algorithm, but can change when upstream identity-defining fields change. It is not a permanent Wiktionary identifier.

Sense-level synonyms and antonyms remain attached to their exact senses. Unsense-disambiguated entry relations retain only the selected low-cardinality families: synonyms, antonyms, hypernyms, hyponyms, and related terms. Derived terms and translations remain outside the core artifact until separately profiled.

The `dictionary` artifact profile preserves dictionary content without search indexes. Published schema 10 artifacts use immutable read-only finalization and must be rebuilt from source rather than migrated in place.
