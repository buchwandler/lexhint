from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("lexhint")
except PackageNotFoundError:
    __version__ = "0+unknown"

from .builder import project_artifact
from .datasets import (
    InstalledDataset,
    available_datasets,
    download_dataset,
    list_installed_datasets,
    remove_dataset,
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
    DomainEvidence,
    Example,
    Form,
    LexicalSegment,
    Pronunciation,
    SemanticDomain,
    Sense,
    WordEvidence,
)

__all__ = [
    "ContextCue",
    "DictionaryEntry",
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
