---
schema_version: 4
id: content-0001
kind: content
type: section
section: introduction_and_goals
title: Introduction and Goals
order: 10
status: accepted
version: 3
body_format: markdown
---

`lexhint` is a Python library and CLI that supplies lexical and dictionary-derived semantic evidence to text-normalization and speech-front-end applications such as `spokenform`. It deliberately does not verbalize text or own speech policy.

## Requirements overview

- Determine common-word membership and frequency rank for supported languages.
- Segment compact identifiers and domain labels into known words and unknown runs.
- Extract compact dictionary senses and explicit semantic topics from Wiktextract/Kaikki data.
- Provide candidate-aware context evidence while excluding the candidate token itself.
- Support both lazy per-word acquisition and complete streamed dictionary builds.
- Expose human-readable CLI output and stable JSON output for automation.

## Quality goals

- Keep the runtime dependency-free beyond the Python standard library.
- Make network use explicit, bounded, cacheable, and avoidable with `--offline`.
- Preserve deterministic normalization, segmentation, storage, and JSON behavior, with
  source and snapshot identities recorded for external data.
- Keep external data separate from the Apache-2.0 code distribution.

## Stakeholders

- Speech and text-normalization consumers need small, explainable evidence objects.
- Application developers need a simple Python API and CLI.
- Maintainers need reproducible builds, tests, and safe data-source handling.
- Distributors need clear boundaries between code licensing and external dictionary data.
