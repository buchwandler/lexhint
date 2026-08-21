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
 
Install published SQLite datasets explicitly with `lexhint dataset download LANGUAGE`. The dataset manager stores language, capability variant, and release version side by side, verifies gzip and SQLite metadata before atomic installation, and never downloads from `Lexicon` or ordinary query commands. Use `dataset list`, `dataset info`, `dataset validate`, and `dataset remove` for local management; `dataset available` and `dataset download` are the networked catalog operations.
