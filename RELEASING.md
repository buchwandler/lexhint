# Releasing Lexhint

Use this checklist for a code release. Lexhint uses a dynamic setuptools-scm version, so
confirm that the checked-out tag resolves to the intended version before publishing.
Git-less source archives resolve to `0+unknown`; they must not masquerade as a released
version.

## Quality checks

Run these from a clean checkout:

```bash
python -m pytest
python -m pytest --cov=lexhint --cov-report=term-missing
python -m pytest --cov=lexhint --cov-branch --cov-report=term-missing
python -m ruff check .
python -m ruff format --check .
python -m mypy lexhint
```

The development-mode test run should also be clean:

```bash
python -X dev -m pytest
```

Check that SQLite connections are closed and no `ResourceWarning` messages are emitted.

## Build and metadata checks

Build both distributions and validate the metadata:

```bash
rm -rf dist build
python -m build
python -m twine check dist/*
```

Inspect the artifacts:

```bash
unzip -l dist/*.whl
tar -tzf dist/*.tar.gz
```

Confirm that `lexhint/py.typed` is packaged. Confirm that generated dictionaries and downloaded word lists are not accidentally included in a code-only release.

For every vendored or externally built data artifact, record the source revision or
snapshot identifier, source SHA-256 where available, schema version, and applicable
license/attribution information separately from the code package. The code-only wheel
must not contain user caches or generated external datasets.

## Clean-wheel smoke test

Install the wheel into a fresh virtual environment and exercise the installed command rather than the source tree:

```bash
python -m venv /tmp/lexhint-release-test
/tmp/lexhint-release-test/bin/python -m pip install dist/*.whl

LEXHINT_CACHE_DIR=/tmp/lexhint-cache \
  /tmp/lexhint-release-test/bin/lexhint --version
LEXHINT_CACHE_DIR=/tmp/lexhint-cache \
  /tmp/lexhint-release-test/bin/lexhint setup en
LEXHINT_CACHE_DIR=/tmp/lexhint-cache \
  /tmp/lexhint-release-test/bin/lexhint word house
LEXHINT_CACHE_DIR=/tmp/lexhint-cache \
  /tmp/lexhint-release-test/bin/lexhint dictionary word compiler
LEXHINT_CACHE_DIR=/tmp/lexhint-cache \
  /tmp/lexhint-release-test/bin/lexhint --offline dictionary word compiler
```

The final dictionary command must replay the cached result without network access. Run one opt-in live smoke test against the current FrequencyWords and Kaikki endpoints when network access is available.

## Publish checklist

Before tagging or publishing:

- Confirm the supported Python versions and CI checks are green.
- Confirm the exact tag commit has passed the full test, development-warning, Ruff,
  format, and MyPy checks; the publish workflow repeats these checks before upload.
- Confirm the release job builds both wheel and sdist and runs `twine check`.
- Confirm the publishing credentials or Trusted Publishing configuration.
- Confirm the package name and resolved version.
- Review the wheel and sdist contents one last time.
- Tag the intended version and create the corresponding release entry.

Keep prebuilt dictionary datasets and their licensing/provenance artifacts separate from a code-only release.
