from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("lexhint")
except PackageNotFoundError:
    __version__ = "0+unknown"

from .builder import build_dictionary, iter_wiktextract_entries
from .dictionary import (
    Dictionary,
    DictionaryFetchError,
    DictionaryIncompatible,
    DictionaryNotInstalled,
    DictionaryOfflineError,
    DictionaryWordNotFound,
    fetch_dictionary_word,
)
from .download import (
    KAIKKI_RAW_URL,
    DownloadError,
    cached_dictionary_path,
    fetch_wordlist,
)
from .lexicon import Lexicon, LexiconNotInstalled
from .models import (
    ContextSupport,
    DictionaryBuildStats,
    DictionaryFetchResult,
    Segment,
    Sense,
    TopicScore,
)

__all__ = [
    "ContextSupport",
    "Dictionary",
    "DictionaryBuildStats",
    "DictionaryIncompatible",
    "DictionaryNotInstalled",
    "DownloadError",
    "KAIKKI_RAW_URL",
    "Lexicon",
    "LexiconNotInstalled",
    "Segment",
    "Sense",
    "TopicScore",
    "__version__",
    "build_dictionary",
    "cached_dictionary_path",
    "fetch_wordlist",
    "iter_wiktextract_entries",
    "DictionaryFetchError",
    "DictionaryFetchResult",
    "DictionaryOfflineError",
    "DictionaryWordNotFound",
    "fetch_dictionary_word",
]
