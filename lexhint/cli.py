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
from .dictionary import Dictionary, DictionaryIncompatible, DictionaryNotInstalled
from .download import KAIKKI_RAW_URL, SUPPORTED_LANGUAGES, DownloadError, fetch_wordlist
from .lexicon import Lexicon, LexiconNotInstalled
from .models import ContextSupport, DictionaryBuildStats, Segment, Sense

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
            "  lexhint dictionary word compiler\n"
            "\n"
            "Use --json for stable machine-readable output. Set LEXHINT_LANGUAGE to change "
            "the default language (en)."
        ),
        formatter_class=_HelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"lexhint {__version__}")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    sub = parser.add_subparsers(dest="command", required=True, title="commands", metavar="COMMAND")

    setup = sub.add_parser(
        "setup",
        help="prepare lexhint for a language",
        description="Fetch the word list needed for normal lexhint use.",
        epilog=(
            "Add --dictionary to also build the compact Wiktionary-derived dictionary. "
            "The dictionary source is large and is streamed by default."
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
        "fetch",
        help="download frequency word lists",
        formatter_class=_HelpFormatter,
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
        help="build and inspect dictionary indexes",
        formatter_class=_HelpFormatter,
    )
    dictionary_sub = dictionary.add_subparsers(
        dest="dictionary_command", required=True, title="commands", metavar="COMMAND"
    )

    build = dictionary_sub.add_parser(
        "build",
        help="build a compact dictionary index",
        description="Stream a Wiktextract/Kaikki JSONL source into a compact SQLite index.",
        epilog=(
            "The source defaults to the official Kaikki raw Wiktextract URL and is "
            "streamed without requiring the FrequencyWords word list."
        ),
        formatter_class=_HelpFormatter,
    )
    build.add_argument(
        "language",
        nargs="?",
        choices=sorted(SUPPORTED_LANGUAGES),
        default=None,
        help="language code (default: en)",
    )
    build.add_argument(
        "source", nargs="?", default=KAIKKI_RAW_URL, help="local JSONL(.gz) path or URL"
    )
    build.add_argument("--output", help="output SQLite path")

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

    return parser


def _extract_output_flags(argv: Sequence[str]) -> tuple[list[str], bool, bool]:
    json_output = False
    no_color = False
    cleaned: list[str] = []
    for value in argv:
        if value == "--json":
            json_output = True
        elif value == "--no-color":
            no_color = True
        else:
            cleaned.append(value)
    return cleaned, json_output, no_color


def _json(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def _human_fetch(language: str, path: Path, style: _Style) -> None:
    print(f"{style.green('✓')} {style.bold(language)} word list  {style.dim(path)}")


def _human_word(word: str, rank: int | None, style: _Style) -> None:
    if rank is None:
        print(f"{style.bold(word)}  {style.yellow('· unknown')}")
        return
    print(f"{style.bold(word)}  {style.green('✓ known')}  {style.dim(f'rank #{rank:,}')}")


def _human_segments(text: str, items: Sequence[Segment], style: _Style) -> None:
    print(style.bold(text))
    width = max((len(item.text) for item in items), default=0)
    for item in items:
        value = item.text
        known = item.known
        rank = item.rank
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
        glosses = sense.glosses
        topics = sense.topics
        print(f"  {style.dim(str(index) + '.')} {style.cyan(pos)}")
        for gloss in glosses:
            print(f"     {gloss}")
        if topics:
            print(f"     {style.dim('topics:')} {', '.join(topics)}")


def _human_context(topic: str, support: ContextSupport | None, style: _Style) -> None:
    if support is None:
        print(f"{style.bold(topic)}  {style.yellow('· no supporting evidence')}")
        return
    score = support.score
    cues = support.cues
    print(f"{style.bold(topic)}  {style.green('✓ supported')}  {style.dim(f'score {score:.3f}')}")
    if cues:
        print(f"  {style.dim('cues:')} {', '.join(cues)}")


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
    language: str,
    source: str,
    *,
    output: str | None,
    show_progress: bool,
) -> tuple[Path, DictionaryBuildStats]:
    callback = _progress if show_progress else None
    try:
        return build_dictionary(
            language,
            source,
            output=output,
            progress=callback,
        )
    finally:
        if show_progress:
            print(file=sys.stderr)


def _run(args: argparse.Namespace, *, json_output: bool, style: _Style) -> int:
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
                language,
                args.source,
                output=None,
                show_progress=sys.stderr.isatty(),
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
                {
                    "language": language,
                    "text": text,
                    "segments": [
                        {"text": item.text, "known": item.known, "rank": item.rank}
                        for item in items
                    ],
                }
            )
        else:
            _human_segments(text, items, style)
        return 0

    if args.command == "dictionary" and args.dictionary_command == "build":
        language = args.language or _default_language()
        if not json_output:
            print(style.bold(f"Building {language} dictionary"))
            print(f"{style.dim('source:')} {args.source}")
        path, stats = _build(
            language,
            args.source,
            output=args.output,
            show_progress=sys.stderr.isatty(),
        )
        if json_output:
            _json({"language": language, "path": str(path), **asdict(stats)})
        else:
            _human_build(path, stats, style)
        return 0

    if args.command == "dictionary" and args.dictionary_command == "word":
        language, word = _language_and_value(
            args.values, explicit_language=args.language, label="dictionary word"
        )
        senses = Dictionary(language, path=args.path).senses(word)
        if json_output:
            _json(
                {
                    "language": language,
                    "word": word,
                    "senses": [
                        {
                            "word": sense.word,
                            "pos": sense.pos,
                            "glosses": sense.glosses,
                            "topics": sense.topics,
                        }
                        for sense in senses
                    ],
                }
            )
        else:
            _human_senses(word, senses, style)
        return 0

    if args.command == "context":
        language, topic, text = _context_values(args.values, explicit_language=args.language)
        support = Dictionary(language, path=args.path).supports(
            text,
            target=_span(text, args.target),
            topic=topic,
        )
        if json_output:
            _json(
                {
                    "language": language,
                    "topic": topic,
                    "supported": support is not None,
                    "evidence": None
                    if support is None
                    else {"score": support.score, "cues": support.cues},
                }
            )
        else:
            _human_context(topic, support, style)
        return 0

    raise AssertionError("unreachable")


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    cleaned_argv, json_output, no_color = _extract_output_flags(raw_argv)

    args = _parser().parse_args(cleaned_argv)
    color_enabled = (
        not no_color
        and not json_output
        and os.environ.get("NO_COLOR") is None
        and sys.stdout.isatty()
    )
    style = _Style(color_enabled)

    try:
        return _run(args, json_output=json_output, style=style)
    except (
        LexiconNotInstalled,
        DictionaryIncompatible,
        DictionaryNotInstalled,
        DownloadError,
        ValueError,
        OSError,
    ) as exc:
        if isinstance(exc, LexiconNotInstalled):
            message = "no word list installed for the requested language"
            hint = "run 'lexhint setup <language>'"
        elif isinstance(exc, DictionaryNotInstalled):
            message = "no dictionary index installed for the requested language"
            hint = "run 'lexhint dictionary build <language>'"
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
