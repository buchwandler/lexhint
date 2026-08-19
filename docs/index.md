# lexhint

`lexhint` provides lexical and dictionary-derived semantic evidence for text-normalization and speech-front-end applications.

It provides:

- common-word membership and frequency ranks;
- segmentation of compact identifiers and domain labels;
- compact dictionary senses and semantic topics;
- candidate-aware context evidence for downstream speech applications.

`lexhint` does not verbalize text. Pronunciation and speech policy remain in the consuming application.

## Quick start

Install the package with its development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Prepare the default English word list and try the CLI:

```bash
lexhint setup
lexhint word house
lexhint segment chatgpt
```

Use `--json` for machine-readable output and `--offline` to prevent dictionary network access.

## Documentation

```{toctree}
:maxdepth: 2

architecture
changelog
```

## Source and project information

- [Project README](https://github.com/buchwandler/lexhint)
- [Data sources and licensing](https://github.com/buchwandler/lexhint/blob/main/DATA_SOURCES.md)
