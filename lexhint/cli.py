from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from .builder import build_dictionary
from .dictionary import Dictionary
from .download import KAIKKI_RAW_URL, SUPPORTED_LANGUAGES, fetch_wordlist
from .lexicon import Lexicon


def _span(text: str, target: str | None) -> tuple[int, int]:
    if target is None:
        raise SystemExit("--target is required")
    start = text.find(target)
    if start < 0:
        raise SystemExit(f"target {target!r} not found in text")
    return start, start + len(target)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lexhint")
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="download one or more 50k frequency word lists")
    fetch.add_argument("languages", nargs="+", choices=sorted(SUPPORTED_LANGUAGES))
    fetch.add_argument("--force", action="store_true")

    word = sub.add_parser("word", help="check common-word membership and rank")
    word.add_argument("language")
    word.add_argument("word")

    segment = sub.add_parser("segment", help="segment an identifier-like string")
    segment.add_argument("language")
    segment.add_argument("text")

    dictionary = sub.add_parser("dictionary", help="build and inspect dictionary indexes")
    dictionary_sub = dictionary.add_subparsers(dest="dictionary_command", required=True)

    build = dictionary_sub.add_parser("build", help="stream a Wiktextract/Kaikki JSONL source")
    build.add_argument("language")
    build.add_argument(
        "source",
        help=("local .jsonl/.jsonl.gz path or URL; Kaikki English raw URL is " + KAIKKI_RAW_URL),
    )
    build.add_argument("--output")
    build.add_argument("--limit", type=int, default=50_000)
    build.add_argument(
        "--auto-fetch-wordlist",
        action="store_true",
        help="download the FrequencyWords list if it is not already cached",
    )

    inspect = dictionary_sub.add_parser("word", help="show compact senses for one word")
    inspect.add_argument("language")
    inspect.add_argument("word")
    inspect.add_argument("--path")

    context = sub.add_parser("context", help="show dictionary-derived context evidence")
    context.add_argument("language")
    context.add_argument("topic")
    context.add_argument("text")
    context.add_argument("--target", required=True, help="literal target substring")
    context.add_argument("--path", help="dictionary SQLite path")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    if args.command == "fetch":
        for language in args.languages:
            print(fetch_wordlist(language, force=args.force))
        return 0

    if args.command == "word":
        lexicon = Lexicon(args.language)
        rank = lexicon.rank(args.word)
        print(json.dumps({"word": args.word, "known": rank is not None, "rank": rank}))
        return 0

    if args.command == "segment":
        lexicon = Lexicon(args.language)
        payload = [
            {"text": item.text, "known": item.known, "rank": item.rank}
            for item in lexicon.segment(args.text)
        ]
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    if args.command == "dictionary" and args.dictionary_command == "build":
        lexicon = Lexicon(args.language, auto_fetch=args.auto_fetch_wordlist)
        path, stats = build_dictionary(
            args.language,
            args.source,
            lexicon=lexicon,
            output=args.output,
            limit=args.limit,
        )
        print(
            json.dumps(
                {
                    "path": str(path),
                    "scanned_entries": stats.scanned_entries,
                    "matched_entries": stats.matched_entries,
                    "words": stats.words,
                    "senses": stats.senses,
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "dictionary" and args.dictionary_command == "word":
        dictionary = Dictionary(args.language, path=args.path)
        payload = [
            {
                "word": sense.word,
                "pos": sense.pos,
                "glosses": sense.glosses,
                "topics": sense.topics,
                "categories": sense.categories,
                "tags": sense.tags,
            }
            for sense in dictionary.senses(args.word)
        ]
        print(json.dumps(payload, ensure_ascii=False))
        return 0

    if args.command == "context":
        dictionary = Dictionary(args.language, path=args.path)
        support = dictionary.supports(
            args.text,
            target=_span(args.text, args.target),
            topic=args.topic,
        )
        print(
            json.dumps(
                None
                if support is None
                else {"topic": support.topic, "score": support.score, "cues": support.cues},
                ensure_ascii=False,
            )
        )
        return 0

    raise AssertionError("unreachable")
