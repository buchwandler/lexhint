# Releasing Lexhint

Use this checklist for a code release. Lexhint publishes the Python package separately from language SQLite artifacts. Runtime commands require a local artifact, either built locally or installed from the dataset distribution.

The package uses dynamic setuptools-scm versioning. A Git-less source archive resolves to `0+unknown` and must never be published.

## Quality checks

Run these from a clean checkout with the declared development and documentation dependencies installed:

```bash
python -m pytest
python -X dev -W error::ResourceWarning -m pytest
python -m pytest \
  --cov=lexhint \
  --cov-branch \
  --cov-report=term-missing \
  --cov-report=xml \
  --cov-fail-under=80
python -m ruff check .
python -m ruff format --check .
python -m mypy lexhint
sphinx-build -W -b html docs docs/_build/html
```

The development-mode run must be free of project-owned resource warnings and unraisable exceptions.

## Build and metadata checks

Build both distributions and validate their metadata:

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

Confirm that `lexhint/py.typed` is packaged. Confirm that the wheel and sdist do not contain user caches, generated dictionaries, downloaded FrequencyWords files, full Kaikki dumps, or ledger runtime state. Record external data revisions, hashes, schema versions, and licensing separately from the code package.

## Version safety

The publication workflow checks out complete Git history and derives the expected package version from the GitHub release tag. For a tag `v0.1.0`, the installed package must report exactly `0.1.0`, never `0+unknown`.

The equivalent local check is:

```bash
EXPECTED_VERSION=0.1.0 \
  python -c 'import os, lexhint; actual = lexhint.__version__; expected = os.environ["EXPECTED_VERSION"]; assert actual == expected and actual != "0+unknown", (expected, actual); print(actual)'
```

## Clean-wheel smoke test without a dataset

Install the wheel into a fresh environment and exercise the installed command rather than the source tree:

```bash
python -m venv /tmp/lexhint-release-test
/tmp/lexhint-release-test/bin/python -m pip install dist/*.whl
/tmp/lexhint-release-test/bin/lexhint --version
/tmp/lexhint-release-test/bin/lexhint --help
/tmp/lexhint-release-test/bin/lexhint dictionary --help
/tmp/lexhint-release-test/bin/lexhint dictionary word --help
/tmp/lexhint-release-test/bin/lexhint dictionary build --help
/tmp/lexhint-release-test/bin/lexhint dictionary status --help
```

Verify controlled missing-artifact behavior:

```bash
set +e
LEXHINT_CACHE_DIR=/tmp/lexhint-empty-cache \
  /tmp/lexhint-release-test/bin/lexhint word house
status=$?
set -e
test "$status" -ne 0
```

The error must identify the missing local artifact and explain how to build or install one. It must not create an artifact silently.

## Fixture-backed artifact smoke test

From the repository checkout, build a small deterministic artifact and exercise the installed CLI against it:

```bash
/tmp/lexhint-release-test/bin/lexhint dictionary build en \
  --source tests/fixtures/kaikki-mini.jsonl \
  --output /tmp/lexhint-en.sqlite3 \
  --no-frequency
/tmp/lexhint-release-test/bin/lexhint word compiler --path /tmp/lexhint-en.sqlite3
/tmp/lexhint-release-test/bin/lexhint segment compilerword --path /tmp/lexhint-en.sqlite3
/tmp/lexhint-release-test/bin/lexhint context "The compiler is 8.3.2." \
  --target 16:21 --path /tmp/lexhint-en.sqlite3
/tmp/lexhint-release-test/bin/lexhint dictionary word compiler \
  --path /tmp/lexhint-en.sqlite3
/tmp/lexhint-release-test/bin/lexhint dictionary status \
  --path /tmp/lexhint-en.sqlite3
/tmp/lexhint-release-test/bin/lexhint --json word compiler \
  --path /tmp/lexhint-en.sqlite3
/tmp/lexhint-release-test/bin/lexhint --json dictionary status \
  --path /tmp/lexhint-en.sqlite3
```

The fixture smoke test verifies the current local, read-only artifact model. Run a live dictionary or FrequencyWords integration smoke test separately and only when network access is intentionally available:

```bash
lexhint dictionary build en
```

## Publish checklist

Before tagging or publishing:

- Confirm the supported Python versions and all CI checks are green.
- Confirm the exact tag commit passed tests, warning checks, coverage, Ruff, format, MyPy, and documentation validation.
- Confirm wheel and sdist metadata and contents.
- Confirm the exact Git tag to package version assertion.
- Confirm package credentials or Trusted Publishing configuration.
- Confirm the code package and dataset distribution remain separate.
- Confirm the releaseledger record is in the correct pre-publication state before publishing and is finalized only after shipment.
- Review data licensing and provenance documentation.
