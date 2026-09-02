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
    DatasetUpdate,
    DatasetVariantSpec,
    InstalledDataset,
    available_datasets,
    check_dataset_updates,
    download_dataset,
    list_installed_datasets,
    remove_dataset,
    update_datasets,
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
    ExternalSenseId,
    Form,
    HeadwordRelation,
    LexicalSegment,
    Pronunciation,
    PronunciationEntry,
    PronunciationGroup,
    RelatedTerm,
    SemanticDomain,
    Sense,
    SenseRecord,
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
    "DatasetUpdate",
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
    "ExternalSenseId",
    "Form",
    "HeadwordRelation",
    "LexicalSegment",
    "project_artifact",
    "Lexicon",
    "LexiconCapabilityError",
    "LexiconCoverageError",
    "LexiconIncompatible",
    "LexiconNotInstalled",
    "RelatedTerm",
    "Pronunciation",
    "PronunciationGroup",
    "PronunciationEntry",
    "SemanticDomain",
    "Sense",
    "SenseRecord",
    "WordEvidence",
    "InstalledDataset",
    "check_dataset_updates",
    "available_datasets",
    "download_dataset",
    "update_datasets",
    "list_installed_datasets",
    "remove_dataset",
    "__version__",
]
