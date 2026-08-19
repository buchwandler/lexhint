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
from .models import ContextCue, LexicalSegment, Sense, TopicEvidence

__all__ = [
    "ContextCue",
    "Dictionary",
    "DictionaryIncompatible",
    "DictionaryNotInstalled",
    "DictionaryOfflineError",
    "Lexicon",
    "LexiconNotInstalled",
    "LexicalSegment",
    "Sense",
    "TopicEvidence",
    "__version__",
]
