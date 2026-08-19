from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import NoReturn

from . import __version__
from .builder import build_dictionary
from .dictionary import (
    Dictionary,
    DictionaryFetchError,
    DictionaryIncompatible,
    DictionaryNotInstalled,
    DictionaryOfflineError,
    fetch_dictionary_word,
)
from .download import KAIKKI_RAW_URL, SUPPORTED_LANGUAGES, DownloadError, fetch_wordlist
from .lexicon import Lexicon, LexiconNotInstalled
from .models import (
    DictionaryBuildStats,
    DictionaryFetchResult,
    LexicalSegment,
    Sense,
    TopicEvidence,
)

_DEFAULT_LANGUAGE = "en"


class _HelpFormatter(argparse.RawDescriptionHelpFormatter):
    def __init__(self, prog: str) -> None:
        super().__init__(prog, max_help_position=28, width=88)


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(2, f"\nerror: {message}\nTry '{self.prog} --help' for help.\n")


class _Style:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def _wrap(self, code: str, value: object) -> str:
        text = str(value)
        if not self.enabled:
            return text
        return f"\033[{code}m{text}\033[0m"

    def bold(self, value: object) -> str:
        return self._wrap("1", value)

    def dim(self, value: object) -> str:
        return self._wrap("2", value)

    def green(self, value: object) -> str:
        return self._wrap("32", value)

    def yellow(self, value: object) -> str:
        return self._wrap("33", value)

    def cyan(self, value: object) -> str:
        return self._wrap("36", value)


def _default_language() -> str:
    value = os.environ.get("LEXHINT_LANGUAGE")
    if value is None:
        return _DEFAULT_LANGUAGE
    return _validate_language(value)


def _span(text: str, target: str | None) -> tuple[int, int]:
    if target is None:
        raise ValueError("--target is required")
    start = text.find(target)
    if start < 0:
        raise ValueError(f"target {target!r} was not found in the text")
    return start, start + len(target)


def _validate_language(language: str) -> str:
    normalized = language.lower().split("-", 1)[0]
    if normalized not in SUPPORTED_LANGUAGES:
        supported = ", ".join(sorted(SUPPORTED_LANGUAGES))
        raise ValueError(f"unsupported language {language!r}; choose one of: {supported}")
    return normalized


def _language_and_value(
    values: Sequence[str],
    *,
    explicit_language: str | None,
    label: str,
) -> tuple[str, str]:
    if explicit_language is not None:
        if len(values) != 1:
            raise ValueError(f"{label} accepts one value when --language is used")
        return _validate_language(explicit_language), values[0]
    if len(values) == 1:
        return _default_language(), values[0]
    if len(values) == 2:
        return _validate_language(values[0]), values[1]
    raise ValueError(f"{label} expects WORD or LANGUAGE WORD")


def _language_and_words(
    values: Sequence[str], *, explicit_language: str | None
) -> tuple[str, tuple[str, ...]]:
    if not values:
        raise ValueError("dictionary fetch expects at least one WORD")
    if explicit_language is not None:
        return _validate_language(explicit_language), tuple(values)
    if len(values) > 1 and values[0].lower().split("-", 1)[0] in SUPPORTED_LANGUAGES:
        return _validate_language(values[0]), tuple(values[1:])
    return _default_language(), tuple(values)


def _context_values(
    values: Sequence[str], *, explicit_language: str | None
) -> tuple[str, str, str]:
    if explicit_language is not None:
        if len(values) != 2:
            raise ValueError("context expects TOPIC TEXT when --language is used")
        return _validate_language(explicit_language), values[0], values[1]
    if len(values) == 2:
        return _default_language(), values[0], values[1]
    if len(values) == 3:
        return _validate_language(values[0]), values[1], values[2]
    raise ValueError("context expects TOPIC TEXT or LANGUAGE TOPIC TEXT")


def _parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        prog="lexhint",
        description="Lexical and dictionary-derived hints for text normalization.",
        epilog=(
            "examples:\n"
            "  lexhint setup\n"
            "  lexhint word house\n"
            "  lexhint word de Haus\n"
            "  lexhint segment chatgpt\n"
            "  lexhint dictionary build en\n"
            "  lexhint dictionary fetch compiler\n"
            "  lexhint dictionary word compiler\n"
            "\n"
            "Use --json for stable machine-readable output. Set LEXHINT_LANGUAGE to change "
            "the default language (en). Use --offline to forbid dictionary network access."
        ),
        formatter_class=_HelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"lexhint {__version__}")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    parser.add_argument("--offline", action="store_true", help="never fetch dictionary data")
    sub = parser.add_subparsers(dest="command", required=True, title="commands", metavar="COMMAND")

    setup = sub.add_parser(
        "setup",
        help="prepare lexhint for a language",
        description="Fetch the word list needed for normal lexhint use.",
        epilog=(
            "Add --dictionary to also build the compact Wiktionary-derived dictionary. "
            "This is an advanced operation: the default Kaikki source is very large and "
            "is streamed line-by-line by the builder."
        ),
        formatter_class=_HelpFormatter,
    )
    setup.add_argument(
        "language",
        nargs="?",
        choices=sorted(SUPPORTED_LANGUAGES),
        default=None,
        help="language code (default: en)",
    )
    setup.add_argument("--dictionary", action="store_true", help="also build the dictionary index")
    setup.add_argument("--source", default=KAIKKI_RAW_URL, help="dictionary JSONL path or URL")
    setup.add_argument("--force", action="store_true", help="re-download the word list")

    fetch = sub.add_parser(
        "fetch", help="download frequency word lists", formatter_class=_HelpFormatter
    )
    fetch.add_argument("languages", nargs="+", choices=sorted(SUPPORTED_LANGUAGES))
    fetch.add_argument("--force", action="store_true", help="re-download cached word lists")

    word = sub.add_parser(
        "word",
        help="check common-word membership and rank",
        usage="lexhint word [--language LANG] [LANGUAGE] WORD",
        formatter_class=_HelpFormatter,
    )
    word.add_argument(
        "values", nargs="+", metavar="WORD", help="word, optionally preceded by language"
    )
    word.add_argument("-l", "--language", choices=sorted(SUPPORTED_LANGUAGES))

    segment = sub.add_parser(
        "segment",
        help="segment an identifier-like string",
        usage="lexhint segment [--language LANG] [LANGUAGE] TEXT",
        formatter_class=_HelpFormatter,
    )
    segment.add_argument(
        "values", nargs="+", metavar="TEXT", help="text, optionally preceded by language"
    )
    segment.add_argument("-l", "--language", choices=sorted(SUPPORTED_LANGUAGES))

    dictionary = sub.add_parser(
        "dictionary",
        help="build, fetch, and inspect dictionary indexes",
        formatter_class=_HelpFormatter,
    )
    dictionary_sub = dictionary.add_subparsers(
        dest="dictionary_command", required=True, title="commands", metavar="COMMAND"
    )

    build = dictionary_sub.add_parser(
        "build",
        help="build a compact dictionary index",
        description=(
            "Stream a Wiktextract/Kaikki JSONL source into a compact SQLite index. "
            "This full-build path is intended for advanced users and maintainers because "
            "the default source is very large."
        ),
        epilog=(
            "The source defaults to the official Kaikki raw Wiktextract URL and is "
            "streamed without requiring the FrequencyWords word list. Use dictionary fetch "
            "for a lightweight per-word cache instead."
        ),
        formatter_class=_HelpFormatter,
    )
    build.add_argument("language", nargs="?", choices=sorted(SUPPORTED_LANGUAGES), default=None)
    build.add_argument(
        "source", nargs="?", default=KAIKKI_RAW_URL, help="local JSONL(.gz) path or URL"
    )
    build.add_argument("--output", help="output SQLite path")

    dictionary_fetch = dictionary_sub.add_parser(
        "fetch", help="cache one or more Kaikki word pages", formatter_class=_HelpFormatter
    )
    dictionary_fetch.add_argument("values", nargs="+", metavar="WORD")
    dictionary_fetch.add_argument("-l", "--language", choices=sorted(SUPPORTED_LANGUAGES))
    dictionary_fetch.add_argument("--path", help="dictionary SQLite path")
    dictionary_fetch.add_argument("--refresh", action="store_true", help="re-fetch cached words")

    inspect = dictionary_sub.add_parser(
        "word",
        help="show compact senses for one word",
        usage="lexhint dictionary word [--language LANG] [LANGUAGE] WORD",
        formatter_class=_HelpFormatter,
    )
    inspect.add_argument(
        "values", nargs="+", metavar="WORD", help="word, optionally preceded by language"
    )
    inspect.add_argument("-l", "--language", choices=sorted(SUPPORTED_LANGUAGES))
    inspect.add_argument("--path", help="dictionary SQLite path")
    inspect.add_argument("--refresh", action="store_true", help="re-fetch the word page")

    context = sub.add_parser(
        "context",
        help="show dictionary-derived context evidence",
        usage="lexhint context [--language LANG] [LANGUAGE] TOPIC TEXT --target TARGET",
        formatter_class=_HelpFormatter,
    )
    context.add_argument("values", nargs="+", metavar="VALUE")
    context.add_argument("-l", "--language", choices=sorted(SUPPORTED_LANGUAGES))
    context.add_argument("--target", required=True, help="literal target substring")
    context.add_argument("--path", help="dictionary SQLite path")
    context.add_argument("--refresh", action="store_true", help="re-fetch context word pages")

    return parser


def _extract_output_flags(argv: Sequence[str]) -> tuple[list[str], bool, bool, bool]:
    json_output = False
    no_color = False
    offline = False
    cleaned: list[str] = []
    for value in argv:
        if value == "--json":
            json_output = True
        elif value == "--no-color":
            no_color = True
        elif value == "--offline":
            offline = True
        else:
            cleaned.append(value)
    return cleaned, json_output, no_color, offline


def _json(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def _human_fetch(language: str, path: Path, style: _Style) -> None:
    print(f"{style.green('✓')} {style.bold(language)} word list  {style.dim(path)}")


def _human_dictionary_fetch(result: DictionaryFetchResult, style: _Style) -> None:
    if result.status == "not_found":
        print(f"{style.yellow('·')} {result.word}  not found")
    else:
        state = "cached" if result.cached else "fetched"
        print(f"{style.green('✓')} {result.word}  {state}  {result.senses} dictionary senses")


def _human_word(word: str, rank: int | None, style: _Style) -> None:
    if rank is None:
        print(f"{style.bold(word)}  {style.yellow('· unknown')}")
        return
    print(f"{style.bold(word)}  {style.green('✓ known')}  {style.dim(f'rank #{rank:,}')}")


def _human_segments(text: str, items: Sequence[LexicalSegment], style: _Style) -> None:
    print(style.bold(text))
    width = max((len(item.text) for item in items), default=0)
    for item in items:
        value = item.text
        known = item.in_lexicon
        rank = item.frequency_rank
        status_text = "✓ known" if known else "· unknown"
        status = style.green(status_text) if known else style.yellow(status_text)
        rank_text = style.dim(f"#{rank:,}") if rank is not None else style.dim("—")
        padding = " " * (9 - len(status_text))
        print(f"  {style.cyan(value.ljust(width))}  {status}{padding}  {rank_text}")


def _human_build(path: Path, stats: DictionaryBuildStats, style: _Style) -> None:
    print(f"{style.green('✓')} dictionary ready  {style.dim(path)}")
    print(
        "  "
        f"{stats.words:,} words · {stats.senses:,} senses · "
        f"{stats.scanned_entries:,} entries scanned"
    )


def _human_senses(word: str, senses: Sequence[Sense], style: _Style) -> None:
    print(style.bold(word))
    if not senses:
        print(f"  {style.yellow('· no dictionary senses found')}")
        return
    for index, sense in enumerate(senses, start=1):
        pos = sense.pos or "sense"
        print(f"  {style.dim(str(index) + '.')} {style.cyan(pos)}")
        for gloss in sense.glosses:
            print(f"     {gloss}")
        if sense.topics:
            print(f"     {style.dim('topics:')} {', '.join(sense.topics)}")


def _human_context(topic: str, support: TopicEvidence | None, style: _Style) -> None:
    if support is None:
        print(f"{style.bold(topic)}  {style.yellow('· no supporting evidence')}")
        return
    score = style.dim(f"score {support.score:.3f}")
    print(f"{style.bold(topic)}  {style.green('✓ supported')}  {score}")
    if support.cues:
        print(f"  {style.dim('cues:')} {', '.join(cue.text for cue in support.cues)}")


def _progress(stats: DictionaryBuildStats) -> None:
    print(
        "\r  "
        f"{stats.scanned_entries:,} entries scanned · "
        f"{stats.words:,} words · {stats.senses:,} senses",
        end="",
        file=sys.stderr,
        flush=True,
    )


def _build(
    language: str, source: str, *, output: str | None, show_progress: bool
) -> tuple[Path, DictionaryBuildStats]:
    callback = _progress if show_progress else None
    try:
        return build_dictionary(language, source, output=output, progress=callback)
    finally:
        if show_progress:
            print(file=sys.stderr)


def _run(args: argparse.Namespace, *, json_output: bool, style: _Style, offline: bool) -> int:
    if args.command == "setup":
        language = args.language or _default_language()
        path = fetch_wordlist(language, force=args.force)
        if json_output and not args.dictionary:
            _json({"language": language, "wordlist": str(path)})
            return 0
        if not json_output:
            print(style.bold(f"Setting up {language}"))
            _human_fetch(language, path, style)
        if args.dictionary:
            if not json_output:
                print(f"{style.dim('→')} building dictionary from {args.source}")
            dictionary_path, stats = _build(
                language, args.source, output=None, show_progress=sys.stderr.isatty()
            )
            if json_output:
                _json(
                    {
                        "language": language,
                        "wordlist": str(path),
                        "dictionary": str(dictionary_path),
                        **asdict(stats),
                    }
                )
            else:
                _human_build(dictionary_path, stats, style)
        elif not json_output:
            print(f"\n{style.green('Ready.')} Try: {style.bold('lexhint word house')}")
        return 0

    if args.command == "fetch":
        payload: list[dict[str, str]] = []
        for language in args.languages:
            path = fetch_wordlist(language, force=args.force)
            payload.append({"language": language, "path": str(path)})
            if not json_output:
                _human_fetch(language, path, style)
        if json_output:
            _json(payload)
        return 0

    if args.command == "word":
        language, word = _language_and_value(
            args.values, explicit_language=args.language, label="word"
        )
        rank = Lexicon(language).rank(word)
        if json_output:
            _json({"language": language, "word": word, "known": rank is not None, "rank": rank})
        else:
            _human_word(word, rank, style)
        return 0

    if args.command == "segment":
        language, text = _language_and_value(
            args.values, explicit_language=args.language, label="segment"
        )
        items = Lexicon(language).segment(text)
        if json_output:
            _json(
                {"language": language, "text": text, "segments": [asdict(item) for item in items]}
            )
        else:
            _human_segments(text, items, style)
        return 0

    if args.command == "dictionary" and args.dictionary_command == "build":
        language = args.language or _default_language()
        if not json_output:
            print(style.bold(f"Building {language}"))
            print(f"{style.dim('source:')} {args.source}")
        path, stats = _build(
            language, args.source, output=args.output, show_progress=sys.stderr.isatty()
        )
        if json_output:
            _json({"language": language, "path": str(path), **asdict(stats)})
        else:
            _human_build(path, stats, style)
        return 0

    if args.command == "dictionary" and args.dictionary_command == "fetch":
        language, words = _language_and_words(args.values, explicit_language=args.language)
        results: list[DictionaryFetchResult] = []
        for word in words:
            results.append(
                fetch_dictionary_word(
                    language,
                    word,
                    path=args.path,
                    refresh=args.refresh,
                    offline=offline,
                )
            )
        if json_output:
            _json({"language": language, "results": [asdict(result) for result in results]})
        else:
            for result in results:
                _human_dictionary_fetch(result, style)
        return 0

    if args.command == "dictionary" and args.dictionary_command == "word":
        language, word = _language_and_value(
            args.values, explicit_language=args.language, label="dictionary word"
        )
        dictionary = Dictionary(
            language, path=args.path, fetch_missing=not offline, offline=offline
        )
        senses = dictionary.senses(word, refresh=args.refresh)
        if json_output:
            _json(
                {"language": language, "word": word, "senses": [asdict(sense) for sense in senses]}
            )
        else:
            _human_senses(word, senses, style)
        return 0

    if args.command == "context":
        language, topic, text = _context_values(args.values, explicit_language=args.language)
        dictionary = Dictionary(
            language, path=args.path, fetch_missing=not offline, offline=offline
        )
        support = dictionary.supports(
            text,
            target=_span(text, args.target),
            topic=topic,
            refresh=args.refresh,
        )
        if json_output:
            _json(
                {
                    "language": language,
                    "topic": topic,
                    "supported": support is not None,
                    "evidence": None
                    if support is None
                    else {
                        "score": support.score,
                        "cues": [asdict(cue) for cue in support.cues],
                    },
                }
            )
        else:
            _human_context(topic, support, style)
        return 0

    raise AssertionError("unreachable")


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    cleaned_argv, json_output, no_color, offline = _extract_output_flags(raw_argv)
    args = _parser().parse_args(cleaned_argv)
    color_enabled = (
        not no_color
        and not json_output
        and os.environ.get("NO_COLOR") is None
        and sys.stdout.isatty()
    )
    style = _Style(color_enabled)

    try:
        return _run(args, json_output=json_output, style=style, offline=offline)
    except (
        LexiconNotInstalled,
        DictionaryIncompatible,
        DictionaryNotInstalled,
        DictionaryFetchError,
        DownloadError,
        ValueError,
        OSError,
    ) as exc:
        if isinstance(exc, LexiconNotInstalled):
            message = "no word list installed for the requested language"
            hint = "run 'lexhint setup <language>'"
        elif isinstance(exc, DictionaryOfflineError):
            message = str(exc)
            hint = "run 'lexhint dictionary fetch <word>' without --offline"
        elif isinstance(exc, DictionaryNotInstalled):
            message = str(exc)
            hint = "run 'lexhint dictionary fetch <word>' or 'lexhint dictionary build <language>'"
        elif isinstance(exc, DictionaryIncompatible):
            message = str(exc)
            hint = "run 'lexhint dictionary build <language>'"
        else:
            message = str(exc)
            hint = None

        if json_output:
            payload: dict[str, str] = {"error": message}
            if hint is not None:
                payload["hint"] = hint
            print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
        else:
            print(f"error: {message}", file=sys.stderr)
            if hint is not None:
                print(f"hint: {hint}", file=sys.stderr)
        return 1
