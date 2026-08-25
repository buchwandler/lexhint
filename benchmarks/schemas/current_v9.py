"""Schema 9 benchmark label retained for before/after comparisons."""

from .current_v8_relations import CurrentV8RelationsAdapter


class CurrentV9Adapter(CurrentV8RelationsAdapter):
    name = "current-v9"
    source_schema_version = "9"
    description = "Pre-schema-10 relation layout used as a comparison baseline."
