from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import asdict
from pathlib import Path
from typing import NoReturn

from . import __version__
from .builder import build_dictionary, project_artifact
from .datasets import (
    DatasetArtifact,
    DatasetError,
    DatasetProgress,
    InstalledDataset,
    available_datasets,
    download_dataset,
    list_installed_datasets,
    remove_dataset,
    resolve_installed_dataset,
    validate_datasets,
)
from .download import KAIKKI_RAW_URL, SUPPORTED_LANGUAGES
from .lexicon import (
    Lexicon,
    LexiconCapabilityError,
    LexiconCoverageError,
    LexiconIncompatible,
    LexiconNotInstalled,
)
from .models import DictionaryBuildStats, DomainEvidence, LexicalSegment, WordEvidence
from .render import (
    DictionaryRenderOptions,
    filter_dictionary_entries,
    render_dictionary_entries,
    resolve_dictionary_fields,
    resolve_pos_filters,
    terminal_render_width,
)
from .schema import PROFILES, normalize_capabilities
from .status import ArtifactStatus, read_artifact_status

_DEFAULT_LANGUAGE = "en"
_DICTIONARY_DETAILS = ("compact", "standard", "full")


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(2, f"\nerror: {message}\nTry '{self.prog} --help' for help.\n")


class _Style:
    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def _wrap(self, code: str, value: object) -> str:
        text = str(value)
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

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
    return os.environ.get("LEXHINT_LANGUAGE", _DEFAULT_LANGUAGE).lower().split("-", 1)[0]


def _language(values: Sequence[str], explicit: str | None) -> tuple[str, str]:
    if explicit:
        if len(values) != 1:
            raise ValueError("one value is required when --language is used")
        return explicit.lower().split("-", 1)[0], values[0]
    if len(values) == 1:
        return _default_language(), values[0]
    if len(values) == 2:
        return values[0].lower().split("-", 1)[0], values[1]
    raise ValueError("expected WORD/TEXT or LANGUAGE WORD/TEXT")


def _target_span(text: str, target: str) -> tuple[int, int]:
    if ":" in target:
        raw_start, raw_end = target.split(":", 1)
        try:
            start, end = int(raw_start), int(raw_end)
        except ValueError as exc:
            raise ValueError("--target must be START:END or a literal substring") from exc
        if not 0 <= start <= end <= len(text):
            raise ValueError("--target span is outside the text")
        return start, end
    start = text.find(target)
    if start < 0:
        raise ValueError(f"target {target!r} was not found in the text")
    return start, start + len(target)


def _artifact_selector(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--variant", help="installed dataset capability variant")
    parser.add_argument("--dataset-version", help="exact installed dataset release version")
    parser.add_argument("--path", help="local SQLite artifact")


def _parser() -> argparse.ArgumentParser:
    parser = _ArgumentParser(
        prog="lexhint", description="Local lexical evidence from SQLite language artifacts."
    )
    parser.add_argument("--version", action="version", version=f"lexhint {__version__}")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    parser.add_argument("--offline", action="store_true", help="forbid build/source network access")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (
        ("word", "show lexical membership and commonness"),
        ("segment", "segment a compact alphabetic string"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("values", nargs="+")
        command.add_argument("-l", "--language", choices=sorted(SUPPORTED_LANGUAGES))
        _artifact_selector(command)

    context = sub.add_parser("context", help="show semantic-domain evidence around a target")
    context.add_argument("text", nargs="+")
    context.add_argument("--target", required=True, help="START:END span or literal target")
    context.add_argument("-l", "--language", choices=sorted(SUPPORTED_LANGUAGES))
    _artifact_selector(context)
    context.add_argument("--window", type=int, default=6)
    context.add_argument("--decay", type=float, default=0.7)
    context.add_argument("--limit", type=int)

    dictionary = sub.add_parser("dictionary", help="build or inspect SQLite language artifacts")
    dictionary_sub = dictionary.add_subparsers(dest="dictionary_command", required=True)
    build = dictionary_sub.add_parser("build", help="build a self-describing local SQLite artifact")
    build.add_argument("language", nargs="?", choices=sorted(SUPPORTED_LANGUAGES), default=None)
    build.add_argument("source_positional", nargs="?", help=argparse.SUPPRESS)
    build.add_argument("--source", dest="source_option", help="dictionary JSONL(.gz) path or URL")
    build.add_argument("--output")
    build.add_argument(
        "--capabilities", help="comma-separated capabilities: lexical,semantic,dictionary"
    )
    build.add_argument("--profile", choices=sorted(PROFILES))
    build.add_argument(
        "--no-frequency", action="store_true", help="disable default FrequencyWords enrichment"
    )
    build.add_argument("--frequency-source", help="custom local or HTTP frequency source")
    build.add_argument(
        "--refresh-frequency",
        action="store_true",
        help="refresh the cached automatic frequency source",
    )

    project = dictionary_sub.add_parser(
        "project", help="create a capability subset from an existing SQLite artifact"
    )
    project.add_argument("source", type=Path)
    project.add_argument("--output", required=True)
    project.add_argument(
        "--capabilities", help="comma-separated capabilities: lexical,semantic,dictionary"
    )
    project.add_argument("--profile", choices=sorted(PROFILES))

    inspect = dictionary_sub.add_parser(
        "word",
        help="show rich dictionary entries",
        epilog=(
            "Dictionary fields: etymology, pronunciations, forms, tags, topics, "
            "examples, synonyms, antonyms. Groups: all, entry, sense, relations."
        ),
    )
    inspect.add_argument("values", nargs="+")
    inspect.add_argument("-l", "--language", choices=sorted(SUPPORTED_LANGUAGES))
    _artifact_selector(inspect)
    inspect.add_argument(
        "--detail",
        choices=_DICTIONARY_DETAILS,
        default=None,
        help="human-readable dictionary detail level (default: standard)",
    )
    inspect.add_argument(
        "--show",
        action="append",
        metavar="FIELDS",
        help="add comma-separated dictionary fields or groups",
    )
    inspect.add_argument(
        "--hide",
        action="append",
        metavar="FIELDS",
        help="remove comma-separated dictionary fields or groups",
    )
    inspect.add_argument(
        "--pos",
        action="append",
        metavar="POS",
        help="show only comma-separated parts of speech",
    )
    inspect.add_argument(
        "--exclude-pos",
        action="append",
        metavar="POS",
        help="exclude comma-separated parts of speech",
    )
    inspect.add_argument("--width", type=int, help="human-output width, from 40 through 240")
    status = dictionary_sub.add_parser("status", help="show SQLite artifact status and counts")
    status.add_argument("language", nargs="?", choices=sorted(SUPPORTED_LANGUAGES), default=None)
    _artifact_selector(status)

    dataset = sub.add_parser("dataset", help="download and manage published datasets")
    dataset_sub = dataset.add_subparsers(dest="dataset_command", required=True)
    download = dataset_sub.add_parser("download", help="download a published dataset")
    download.add_argument("language", choices=sorted(SUPPORTED_LANGUAGES))
    download.add_argument("--variant", default="runtime")
    download.add_argument("--version", dest="dataset_version")
    download.add_argument("--force", action="store_true")
    available = dataset_sub.add_parser("available", help="list published datasets")
    available.add_argument("--language", choices=sorted(SUPPORTED_LANGUAGES))
    available.add_argument("--version", dest="dataset_version")
    info = dataset_sub.add_parser("info", help="show an installed dataset")
    info.add_argument("language", choices=sorted(SUPPORTED_LANGUAGES))
    info.add_argument("--variant")
    info.add_argument("--version", dest="dataset_version")
    listing = dataset_sub.add_parser("list", help="list installed datasets")
    listing.add_argument("--language", choices=sorted(SUPPORTED_LANGUAGES))
    remove = dataset_sub.add_parser("remove", help="remove installed dataset artifacts")
    remove.add_argument("language", choices=sorted(SUPPORTED_LANGUAGES))
    remove.add_argument("--variant", required=True)
    remove.add_argument("--version", dest="dataset_version")
    validate = dataset_sub.add_parser("validate", help="validate installed dataset artifacts")
    validate.add_argument("language", nargs="?", choices=sorted(SUPPORTED_LANGUAGES))
    validate.add_argument("--variant")
    validate.add_argument("--version", dest="dataset_version")

    return parser


def _json(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def _word(info: WordEvidence, style: _Style) -> None:
    status = style.green("known") if info.known else style.yellow("unknown")
    print(f"{style.bold(info.text)}  {status}")
    if info.known:
        rank = "#" + format(info.frequency_rank, ",") if info.frequency_rank is not None else "—"
        print(f"rank      {rank}")
        if info.frequency_count is not None:
            print(f"count     {info.frequency_count:,}")


def _segments(text: str, values: Sequence[LexicalSegment], style: _Style) -> None:
    print(style.bold(text))
    for value in values:
        status = style.green("known") if value.known else style.yellow("unknown")
        print(f"  {style.cyan(value.text)}  {status}")


def _context(values: Sequence[DomainEvidence], style: _Style) -> None:
    for evidence in values:
        print(f"{style.bold(evidence.domain.value)}  {evidence.score:.2f}")
        for cue in evidence.cues:
            print(f"  {cue.text}  distance={cue.distance}  weight={cue.weight:.2f}")


def _status(info: ArtifactStatus, style: _Style) -> None:
    values = info.as_dict()
    counts = values["counts"]
    print(style.bold("Lexhint database"))
    print(f"  language      {values['language']}")
    print(f"  schema        {values['schema_version']}")
    print(f"  coverage      {values['coverage']}")
    print(f"  profile       {values['profile']}")
    print(f"  capabilities  {', '.join(values['capabilities'])}")
    print(f"  lexemes       {counts['lexemes']:,}")
    print(
        f"  semantic      {counts['semantic_rows']:,}"
        if counts["semantic_rows"] is not None
        else "  semantic      not included"
    )
    print(
        f"  dictionary    {counts['entries']:,} entries, {counts['senses']:,} senses"
        if counts["entries"] is not None
        else "  dictionary    not included"
    )
    print(f"  frequency     {counts['frequency_lexemes']:,} lexemes ranked")
    print(f"  built         {values['built_at']}")
    print(f"  size          {values['size_bytes']:,} bytes")
    print(f"  path          {values['path']}")


def _dataset_value(value: DatasetArtifact | InstalledDataset) -> dict[str, object]:
    return value.as_dict()


def _dataset_progress(progress: DatasetProgress) -> None:
    total = f"/{progress.total_bytes:,} bytes" if progress.total_bytes is not None else ""
    print(f"{progress.phase}: {progress.downloaded_bytes:,}{total}", file=sys.stderr)


def _run_dataset(args: argparse.Namespace, *, json_output: bool) -> int:
    if args.dataset_command == "download":
        result = download_dataset(
            args.language,
            variant=args.variant,
            version=args.dataset_version,
            force=args.force,
            offline=args.offline,
            progress=None if json_output else _dataset_progress,
        )
        payload = _dataset_value(result)
        if json_output:
            _json(payload)
        elif result.already_installed:
            print(
                f"Already installed {result.language}/{result.variant} "
                f"{result.dataset_version}: {result.path}"
            )
        else:
            print(
                f"Installed {result.language}/{result.variant} "
                f"{result.dataset_version}: {result.path}"
            )
        return 0
    if args.dataset_command == "available":
        remote_items = available_datasets(
            language=args.language, version=args.dataset_version, offline=args.offline
        )
        payload = {"available": [_dataset_value(value) for value in remote_items]}
        if json_output:
            _json(payload)
        else:
            for remote_item in remote_items:
                print(
                    f"{remote_item.language} {remote_item.variant} {remote_item.dataset_version} "
                    f"{', '.join(remote_item.capabilities)} {remote_item.compressed_size:,} bytes"
                )
        return 0
    if args.dataset_command == "list":
        installed_items = list_installed_datasets(args.language)
        selected: dict[str, InstalledDataset] = {}
        for installed_item in installed_items:
            with suppress(DatasetError):
                selected[installed_item.language] = resolve_installed_dataset(
                    installed_item.language
                )
        payload_items: list[dict[str, object]] = []
        for installed_item in installed_items:
            value = _dataset_value(installed_item)
            value["selected"] = selected.get(installed_item.language) == installed_item
            payload_items.append(value)
        payload = {"installed": payload_items}
        if json_output:
            _json(payload)
        else:
            for installed_item, value in zip(installed_items, payload_items, strict=True):
                marker = " *" if value["selected"] else ""
                print(
                    f"{installed_item.language} {installed_item.variant} "
                    f"{installed_item.dataset_version} {', '.join(installed_item.capabilities)} "
                    f"{installed_item.size_bytes:,} bytes{marker}"
                )
        return 0
    if args.dataset_command == "info":
        selected_item = resolve_installed_dataset(
            args.language, variant=args.variant, version=args.dataset_version
        )
        installed_values = [
            _dataset_value(value) for value in list_installed_datasets(args.language)
        ]
        payload = _dataset_value(selected_item)
        payload["installed_variants"] = installed_values
        if json_output:
            _json(payload)
        else:
            for key, field_value in payload.items():
                if key != "installed_variants":
                    print(f"{key}: {field_value}")
            print("installed variants:")
            for value in installed_values:
                print(f"  {value['variant']} {value['dataset_version']} {value['path']}")
        return 0
    if args.dataset_command == "remove":
        removed = remove_dataset(args.language, variant=args.variant, version=args.dataset_version)
        payload = {"removed": [str(path) for path in removed]}
        if json_output:
            _json(payload)
        else:
            for path in removed:
                print(f"Removed {path}")
        return 0
    if args.dataset_command == "validate":
        valid_items = validate_datasets(
            args.language, variant=args.variant, version=args.dataset_version
        )
        payload = {"valid": [_dataset_value(value) for value in valid_items]}
        if json_output:
            _json(payload)
        else:
            for valid_item in valid_items:
                print(
                    f"Valid {valid_item.language}/{valid_item.variant}/"
                    f"{valid_item.dataset_version}: {valid_item.path}"
                )
        return 0
    raise AssertionError("unreachable")


def _run(args: argparse.Namespace, *, style: _Style, json_output: bool) -> int:
    if args.command == "dataset":
        return _run_dataset(args, json_output=json_output)
    if args.command == "word":
        language, word = _language(args.values, args.language)
        lexicon = Lexicon(
            language, variant=args.variant, dataset_version=args.dataset_version, path=args.path
        )
        info = lexicon.word(word)
        if json_output:
            _json({"language": language, **asdict(info)})
        else:
            _word(info, style)
        return 0
    if args.command == "segment":
        language, text = _language(args.values, args.language)
        lexicon = Lexicon(
            language, variant=args.variant, dataset_version=args.dataset_version, path=args.path
        )
        values = lexicon.segment(text)
        if json_output:
            _json(
                {
                    "language": language,
                    "text": text,
                    "segments": [asdict(value) for value in values],
                }
            )
        else:
            _segments(text, values, style)
        return 0
    if args.command == "context":
        language = (args.language or _default_language()).lower().split("-", 1)[0]
        text = " ".join(args.text)
        lexicon = Lexicon(
            language, variant=args.variant, dataset_version=args.dataset_version, path=args.path
        )
        domains = lexicon.context_domains(
            text,
            target=_target_span(text, args.target),
            window=args.window,
            decay=args.decay,
            limit=args.limit,
        )
        if json_output:
            _json(
                {
                    "language": language,
                    "domains": [
                        {
                            "domain": value.domain.value,
                            "score": value.score,
                            "cues": [asdict(cue) for cue in value.cues],
                        }
                        for value in domains
                    ],
                }
            )
        else:
            _context(domains, style)
        return 0
    if args.dictionary_command == "project":
        path = project_artifact(
            args.source,
            output=args.output,
            capabilities=args.capabilities,
            profile=args.profile,
        )
        if json_output:
            _json({"path": str(path)})
        else:
            print(f"Projected Lexhint database: {path}")
        return 0
    if args.dictionary_command == "build":
        language = args.language or _default_language()
        source = args.source_option or args.source_positional or KAIKKI_RAW_URL
        selection = normalize_capabilities(args.capabilities, profile=args.profile)
        print("Building Lexhint database", file=sys.stderr)
        print(f"  language      {language}", file=sys.stderr)
        print(f"  capabilities  {', '.join(selection.capabilities)}", file=sys.stderr)
        print(f"  dictionary    {source}", file=sys.stderr)
        frequency = (
            "disabled" if args.no_frequency else args.frequency_source or "FrequencyWords automatic"
        )
        print(f"  frequency     {frequency}", file=sys.stderr)
        print(f"  output        {args.output or 'default cache artifact'}", file=sys.stderr)

        def report(stats: DictionaryBuildStats) -> None:
            print(
                f"  scanned {stats.scanned_entries:,}   lexemes {stats.words:,}   "
                f"entries {stats.kept_entries:,}   senses {stats.senses:,}",
                file=sys.stderr,
            )

        path, stats = build_dictionary(
            language,
            source,
            output=args.output,
            capabilities=args.capabilities,
            profile=args.profile,
            frequency_source=args.frequency_source,
            no_frequency=args.no_frequency,
            refresh_frequency=args.refresh_frequency,
            offline=args.offline,
            progress=report,
        )
        if json_output:
            _json({"language": language, "path": str(path), **asdict(stats)})
        else:
            print(f"Built {language} Lexhint database")
            print(f"  capabilities  {', '.join(stats.capabilities)}")
            print(f"  lexemes       {stats.words:,}")
            print(
                f"  semantic      {stats.semantic_rows:,}"
                if "semantic" in stats.capabilities
                else "  semantic      not included"
            )
            print(
                f"  dictionary    {stats.entries:,}"
                if "dictionary" in stats.capabilities
                else "  dictionary    not included"
            )
            print(f"  output        {path}")
        return 0
    if args.dictionary_command == "word":
        presentation_options = (
            args.detail is not None or args.show or args.hide or args.width is not None
        )
        if json_output and presentation_options:
            if args.detail is not None and not (args.show or args.hide or args.width):
                raise ValueError(
                    "--detail only applies to human-readable output; omit it when using --json"
                )
            raise ValueError(
                "--detail/--show/--hide/--width are human-output options "
                "and cannot be used with --json"
            )
        language, word = _language(args.values, args.language)
        lexicon = Lexicon(
            language, variant=args.variant, dataset_version=args.dataset_version, path=args.path
        )
        original_entries = lexicon.entries(word)
        include_pos, exclude_pos = resolve_pos_filters(args.pos, args.exclude_pos)
        entries = filter_dictionary_entries(
            original_entries, include=include_pos, exclude=exclude_pos
        )
        if json_output:
            _json(
                {
                    "language": language,
                    "word": word,
                    "entries": [asdict(value) for value in entries],
                }
            )
        else:
            if not entries and include_pos is not None and original_entries:
                print(style.bold(word))
                selectors = ", ".join(sorted(include_pos))
                print(f"  {style.yellow(f'no dictionary entries matched --pos {selectors}')}")
            elif not entries and exclude_pos and original_entries:
                print(style.bold(word))
                selectors = ", ".join(sorted(exclude_pos))
                message = f"no dictionary entries remained after --exclude-pos {selectors}"
                print(f"  {style.yellow(message)}")
            else:
                detail = args.detail or "standard"
                options = DictionaryRenderOptions(
                    fields=resolve_dictionary_fields(detail, show=args.show, hide=args.hide),
                    include_pos=include_pos,
                    exclude_pos=exclude_pos,
                    width=terminal_render_width(args.width),
                )
                print(render_dictionary_entries(word, entries, options=options, detail=detail))
        return 0
    if args.dictionary_command == "status":
        language = args.language
        artifact_info = read_artifact_status(
            language,
            variant=args.variant,
            dataset_version=args.dataset_version,
            path=args.path,
        )
        if json_output:
            _json(artifact_info.as_dict())
        else:
            _status(artifact_info, style)
        return 0
    raise AssertionError("unreachable")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(list(sys.argv[1:] if argv is None else argv))
    json_output = args.json
    style = _Style(
        not args.no_color
        and not json_output
        and os.environ.get("NO_COLOR") is None
        and sys.stdout.isatty()
    )
    try:
        return _run(args, style=style, json_output=json_output)
    except (
        DatasetError,
        LexiconCapabilityError,
        LexiconCoverageError,
        LexiconIncompatible,
        LexiconNotInstalled,
        ValueError,
        OSError,
        RuntimeError,
    ) as exc:
        message = str(exc)
        if isinstance(exc, DatasetError) or (
            isinstance(exc, LexiconNotInstalled) and "installed for" in message
        ):
            hint = "run 'lexhint dataset download <language>'"
        elif isinstance(exc, (LexiconIncompatible, LexiconCoverageError, LexiconNotInstalled)):
            hint = "run 'lexhint dictionary build <language>'"
        else:
            hint = None
        if json_output:
            payload = {"error": message}
            if hint:
                payload["hint"] = hint
            print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
        else:
            print(f"error: {message}", file=sys.stderr)
            if hint:
                print(f"hint: {hint}", file=sys.stderr)
        return 1
