"""Schema 10 read-only finalized benchmark layout."""

from .schema10_candidate import Schema10CandidateAdapter


class CurrentV9ReadonlyFinalizedAdapter(Schema10CandidateAdapter):
    name = "current-v9-readonly-finalized"
    source_schema_version = "10"
    description = "Schema 10 candidate after immutable-artifact index finalization."
