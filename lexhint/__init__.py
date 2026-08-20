from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("lexhint")
except PackageNotFoundError:
    __version__ = "0+unknown"

from .dictionary import (
    Dictionary,
    DictionaryCoverageError,
    DictionaryIncompatible,
    DictionaryNotInstalled,
    DictionaryOfflineError,
)
from .models import (
    ContextCue,
    DictionaryEntry,
    Example,
    Form,
    LexicalSegment,
    Pronunciation,
    Sense,
    TopicEvidence,
    WordInfo,
)

__all__ = [
    "ContextCue",
    "Dictionary",
    "DictionaryCoverageError",
    "DictionaryEntry",
    "DictionaryIncompatible",
    "DictionaryNotInstalled",
    "DictionaryOfflineError",
    "Example",
    "Form",
    "LexicalSegment",
    "Pronunciation",
    "Sense",
    "TopicEvidence",
    "WordInfo",
    "__version__",
]
