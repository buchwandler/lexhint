from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("lexhint")
except PackageNotFoundError:
    __version__ = "0+unknown"

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
    "Lexicon",
    "LexiconCapabilityError",
    "LexiconCoverageError",
    "LexiconIncompatible",
    "LexiconNotInstalled",
    "Pronunciation",
    "SemanticDomain",
    "Sense",
    "WordEvidence",
    "__version__",
]
