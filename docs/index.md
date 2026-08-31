# Lexhint

Lexhint is a local lexical-evidence engine backed by self-describing SQLite artifacts.

It provides lexical membership, frequency enrichment, compact-string segmentation, stable semantic-domain evidence, and optional rich dictionary entries. It does not speak or normalize text.

```{toctree}
:maxdepth: 2

architecture
changelog
```

See the [README](https://github.com/buchwandler/lexhint) for installation, build commands, API examples, and data-source boundaries.

## Dataset lifecycle

Install published SQLite datasets explicitly with `lexhint dataset download LANGUAGE`. The client reads the `lexhint-datasets` catalog, caches its validated bytes under `LEXHINT_CACHE_DIR` (or the platform cache directory), and downloads selected assets from immutable GitHub Releases. Online catalog reads use conditional refresh metadata and fall back to a valid cached catalog on transport failure. `--offline dataset available` and `--offline dataset check` read the cache without network access. The catalog is an index only; detailed provenance remains in each release's `datasets-v2.json`. Exact schema equality is required, and historical releases remain reachable through compatible catalog entries or the compatibility Releases API fallback. The dataset manager stores language, capability variant, and release version side by side, verifies gzip and SQLite metadata before atomic installation, and never downloads from `Lexicon` or ordinary query commands. Use `dataset list`, `dataset info`, `dataset validate`, and `dataset remove` for local management; `dataset available` lists all compatible catalog artifacts, `dataset check` reports updates for installed slots, and `dataset update` updates all installed slots or selected language and variant filters, removing superseded versions after successful installation.
