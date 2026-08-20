from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("lexhint")
except PackageNotFoundError:
    __version__ = "0+unknown"

from .dictionary import (
    Dictionary,
    DictionaryIncompatible,
    DictionaryNotInstalled,
    DictionaryOfflineError,
)
from .lexicon import Lexicon, LexiconNotInstalled
from .models import (
    ContextCue,
    DictionaryEntry,
    Example,
    Form,
    LexicalSegment,
    Pronunciation,
    Sense,
    TopicEvidence,
)

__all__ = [
    "ContextCue",
    "Dictionary",
    "DictionaryEntry",
    "DictionaryIncompatible",
    "DictionaryNotInstalled",
    "DictionaryOfflineError",
    "Example",
    "Form",
    "Lexicon",
    "LexiconNotInstalled",
    "LexicalSegment",
    "Pronunciation",
    "Sense",
    "TopicEvidence",
    "__version__",
]
