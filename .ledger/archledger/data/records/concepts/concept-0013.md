---
schema_version: 4
id: concept-0013
kind: concept
type: concept
title: Explicit immutable managed dataset artifacts
status: accepted
section: cross_cutting_concepts
order: 10
version: 2
applies_to: []
body_format: markdown
---
Lexhint treats published datasets as explicit, immutable local artifacts rather than package-installed Python models. The dataset manager stores artifacts by normalized language, capability variant, and exact release version under the persistent data directory. Downloads stream gzip data, verify manifest hashes, sizes, schema, language, coverage, and capabilities, then atomically install the database and sidecar metadata. Runtime Lexicon construction resolves only installed files and never contacts the network automatically. The highest-capability compatible installed variant is selected by default, while callers may pin a variant and release version.
