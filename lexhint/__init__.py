from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("lexhint")
except PackageNotFoundError:
    __version__ = "0+unknown"

from .builder import project_artifact
from .datasets import (
    DATASET_VARIANT_NAMES,
    DATASET_VARIANTS,
    DEFAULT_DATASET_VARIANT,
    DatasetVariantSpec,
    InstalledDataset,
    available_datasets,
    download_dataset,
    list_installed_datasets,
    remove_dataset,
)
from .languages import (
    LOCALES,
    SUPPORTED_BASE_LANGUAGES,
    LocaleSpec,
    locale_spec,
    normalize_language,
    normalize_locale,
    supported_base_languages,
)
from .lexicon import (
    Lexicon,
    LexiconCapabilityError,
    LexiconCoverageError,
    LexiconIncompatible,
    LexiconNotInstalled,
)
from .models import (
    ContextCue,
    DictionaryEntry,
    DictionarySearchHit,
    DomainEvidence,
    Example,
    Form,
    LexicalSegment,
    Pronunciation,
    RelatedTerm,
    SemanticDomain,
    Sense,
    WordEvidence,
)
from .store import SCHEMA_VERSION

__all__ = [
    "ContextCue",
    "SCHEMA_VERSION",
    "DATASET_VARIANTS",
    "DATASET_VARIANT_NAMES",
    "DEFAULT_DATASET_VARIANT",
    "DatasetVariantSpec",
    "LOCALES",
    "LocaleSpec",
    "SUPPORTED_BASE_LANGUAGES",
    "locale_spec",
    "normalize_language",
    "normalize_locale",
    "supported_base_languages",
    "DictionaryEntry",
    "DictionarySearchHit",
    "DomainEvidence",
    "Example",
    "Form",
    "LexicalSegment",
    "project_artifact",
    "Lexicon",
    "LexiconCapabilityError",
    "LexiconCoverageError",
    "LexiconIncompatible",
    "LexiconNotInstalled",
    "RelatedTerm",
    "Pronunciation",
    "SemanticDomain",
    "Sense",
    "WordEvidence",
    "InstalledDataset",
    "available_datasets",
    "download_dataset",
    "list_installed_datasets",
    "remove_dataset",
    "__version__",
]
