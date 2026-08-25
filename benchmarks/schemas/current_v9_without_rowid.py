"""Schema 9 benchmark layout with compact compound-key tables."""

from .schema10_candidate import Schema10CandidateAdapter


class CurrentV9WithoutRowidAdapter(Schema10CandidateAdapter):
    name = "current-v9-without-rowid"
    source_schema_version = "9"
    description = "Schema 9 logical workload with compact compound-key tables."
