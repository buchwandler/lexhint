from __future__ import annotations

import re
import shutil
import textwrap
from collections.abc import Sequence
from dataclasses import dataclass

from .languages import locale_spec
from .models import DictionaryEntry, Form, Pronunciation, RelatedTerm, Sense
from .terminal import TerminalStyle

DICTIONARY_FIELDS = frozenset(
    {
        "etymology",
        "pronunciations",
        "forms",
        "tags",
        "topics",
        "examples",
        "synonyms",
        "antonyms",
    }
)

DETAIL_FIELDS: dict[str, frozenset[str]] = {
    "compact": frozenset(),
    "standard": frozenset({"forms", "pronunciations", "tags", "topics"}),
    "full": DICTIONARY_FIELDS,
}

FIELD_ALIASES = {
    "pronunciation": "pronunciations",
    "form": "forms",
    "tag": "tags",
    "topic": "topics",
    "example": "examples",
    "synonym": "synonyms",
    "antonym": "antonyms",
}

FIELD_GROUPS = {
    "all": DICTIONARY_FIELDS,
    "entry": frozenset({"etymology", "pronunciations", "forms"}),
    "sense": frozenset({"tags", "topics", "examples", "synonyms", "antonyms"}),
    "relations": frozenset({"synonyms", "antonyms"}),
}

_VALID_FIELDS = ", ".join(sorted(DICTIONARY_FIELDS))


@dataclass(frozen=True, slots=True)
class DictionaryRenderOptions:
    fields: frozenset[str]
    include_pos: frozenset[str] | None = None
    exclude_pos: frozenset[str] = frozenset()
    width: int = 100
    locale: str | None = None
    color: bool = False


def split_csv(values: Sequence[str] | None) -> tuple[str, ...]:
    result: list[str] = []
    for value in values or ():
        result.extend(part.strip() for part in value.split(","))
    return tuple(result)


def normalize_dictionary_field(value: str) -> str:
    normalized = value.strip().lower()
    normalized = FIELD_ALIASES.get(normalized, normalized)
    if normalized not in DICTIONARY_FIELDS and normalized not in FIELD_GROUPS:
        raise ValueError(f"unknown dictionary field {value!r}; valid fields: {_VALID_FIELDS}")
    return normalized


def parse_dictionary_fields(values: Sequence[str] | None) -> frozenset[str]:
    fields: set[str] = set()
    for value in split_csv(values):
        normalized = normalize_dictionary_field(value)
        fields.update(FIELD_GROUPS.get(normalized, (normalized,)))
    return frozenset(fields)


def resolve_dictionary_fields(
    detail: str,
    *,
    show: Sequence[str] | None = None,
    hide: Sequence[str] | None = None,
) -> frozenset[str]:
    try:
        fields = set(DETAIL_FIELDS[detail])
    except KeyError as exc:
        raise ValueError(f"unknown dictionary detail {detail!r}") from exc
    shown = parse_dictionary_fields(show)
    hidden = parse_dictionary_fields(hide)
    conflict = sorted(shown & hidden)
    if conflict:
        raise ValueError(f"dictionary field {conflict[0]!r} is present in both --show and --hide")
    fields.update(shown)
    fields.difference_update(hidden)
    return frozenset(fields)


def normalize_pos(value: str) -> str:
    normalized = re.sub(r"[\s_-]+", " ", value.strip().lower())
    if not normalized:
        raise ValueError("POS selector must not be empty")
    return normalized


def parse_pos_selectors(values: Sequence[str] | None) -> frozenset[str]:
    return frozenset(normalize_pos(value) for value in split_csv(values))


def resolve_pos_filters(
    include: Sequence[str] | None = None,
    exclude: Sequence[str] | None = None,
) -> tuple[frozenset[str] | None, frozenset[str]]:
    included_values = split_csv(include)
    excluded = parse_pos_selectors(exclude)
    included = parse_pos_selectors(included_values) if included_values else None
    if included is not None:
        conflict = sorted(included & excluded)
        if conflict:
            raise ValueError(f"POS {conflict[0]!r} is present in both --pos and --exclude-pos")
    return included, excluded


def filter_dictionary_entries(
    entries: Sequence[DictionaryEntry],
    *,
    include: frozenset[str] | None = None,
    exclude: frozenset[str] = frozenset(),
) -> tuple[DictionaryEntry, ...]:
    return tuple(
        entry
        for entry in entries
        if (include is None or normalize_pos(entry.pos) in include)
        and normalize_pos(entry.pos) not in exclude
    )


def terminal_render_width(width: int | None = None) -> int:
    if width is not None:
        if not 40 <= width <= 240:
            raise ValueError("--width must be between 40 and 240")
        return width
    terminal_width = shutil.get_terminal_size(fallback=(100, 24)).columns
    return max(40, min(terminal_width, 100))


def _wrap(text: str, width: int, *, initial: str, subsequent: str) -> list[str]:
    wrapper = textwrap.TextWrapper(
        width=max(width, len(initial) + 1, len(subsequent) + 1),
        initial_indent=initial,
        subsequent_indent=subsequent,
        break_long_words=False,
        break_on_hyphens=False,
    )
    return wrapper.wrap(" ".join(text.split())) or [initial.rstrip()]


def _wrap_value(text: str, width: int, indent: str) -> list[str]:
    return _wrap(text, width, initial=indent, subsequent=indent)


def _wrap_labeled(
    label: str,
    values: Sequence[str | RelatedTerm],
    width: int,
    indent: str,
    locale: str | None = None,
) -> list[str]:
    formatted: list[str] = []
    for value in values:
        if isinstance(value, str):
            formatted.append(value)
            continue
        regional_label = _regional_label(value.tags, locale)
        formatted.append(f"{regional_label}: {value.word}" if regional_label else value.word)
    text = ", ".join(formatted)
    if not text:
        return []
    initial = f"{indent}{label}: "
    subsequent = " " * len(initial)
    return _wrap(text, width, initial=initial, subsequent=subsequent)


def _unique_forms(values: Sequence[DictionaryEntry]) -> tuple[Form, ...]:
    seen: set[tuple[str, tuple[str, ...]]] = set()
    result: list[Form] = []
    for entry in values:
        for form in entry.forms:
            key = (form.form, form.tags)
            if key not in seen:
                seen.add(key)
                result.append(form)
    return tuple(result)


def _unique_pronunciations(values: Sequence[DictionaryEntry]) -> tuple[Pronunciation, ...]:
    seen: set[tuple[str, tuple[str, ...]]] = set()
    result: list[Pronunciation] = []
    for entry in values:
        for pronunciation in entry.pronunciations:
            key = (pronunciation.ipa, pronunciation.tags)
            if key not in seen:
                seen.add(key)
                result.append(pronunciation)
    return tuple(result)


def _regional_label(tags: Sequence[str], locale: str | None) -> str | None:
    if locale is None:
        return None
    spec = locale_spec("en", locale)
    assert spec is not None
    normalized = {tag.casefold() for tag in tags}
    if locale == "GB" and normalized & {"us", "american", "american-english", "american english"}:
        return "American English"
    if locale == "US" and normalized & {"uk", "british", "british-english", "british english"}:
        return "British English"
    return None


def _format_form(form: Form, locale: str | None = None) -> str:
    label = _regional_label(form.tags, locale)
    prefix = f"{label}: " if label else ""
    suffix = f" [{', '.join(form.tags)}]" if form.tags else ""
    return f"{prefix}{form.form}{suffix}"


def _format_pronunciation(pronunciation: Pronunciation, locale: str | None = None) -> str:
    label = _regional_label(pronunciation.tags, locale)
    prefix = f"{label}: " if label else ""
    suffix = f" [{', '.join(pronunciation.tags)}]" if pronunciation.tags else ""
    return f"{prefix}{pronunciation.ipa}{suffix}"


def _append_block(lines: list[str], block: Sequence[str]) -> None:
    if not block:
        return
    if lines and lines[-1] != "":
        lines.append("")
    lines.extend(block)


def _style_sense_number(lines: list[str], number: int, style: TerminalStyle) -> list[str]:
    if not lines:
        return lines
    prefix = f"    {number}. "
    if lines[0].startswith(prefix):
        lines[0] = "    " + style.cyan(f"{number}.") + " " + lines[0][len(prefix) :]
    elif lines[0] == f"    {number}.":
        lines[0] = "    " + style.cyan(f"{number}.")
    return lines


def _style_label(
    lines: list[str],
    *,
    indent: str,
    label: str,
    style: TerminalStyle,
) -> list[str]:
    if not lines:
        return lines
    prefix = f"{indent}{label}: "
    if lines[0].startswith(prefix):
        lines[0] = indent + style.dim_cyan(f"{label}:") + " " + lines[0][len(prefix) :]
    return lines


def _render_etymology(etymology: str, width: int, style: TerminalStyle) -> list[str]:
    lines = [f"    {style.cyan('etymology')}"]
    normalized = etymology.replace("\r\n", "\n").replace("\r", "\n")
    for source_line in normalized.split("\n"):
        if source_line.strip():
            lines.extend(_wrap_value(source_line, width, "      "))
        else:
            lines.append("")
    return lines


def _render_examples(sense: Sense, width: int, style: TerminalStyle) -> list[str]:
    lines = [f"       {style.cyan('examples')}"]
    for example in sense.examples:
        lines.extend(
            _wrap(
                example.text,
                width,
                initial="         - ",
                subsequent="           ",
            )
        )
        if example.translation:
            translation = _wrap_value(example.translation, width, "           translation: ")
            lines.extend(
                _style_label(
                    translation,
                    indent="           ",
                    label="translation",
                    style=style,
                )
            )
    return lines


def _render_sense(
    sense: Sense,
    number: int,
    fields: frozenset[str],
    width: int,
    locale: str | None,
    style: TerminalStyle,
) -> list[str]:
    lines: list[str] = []
    glosses = tuple(gloss for gloss in sense.glosses if gloss)
    if glosses:
        sense_lines = _wrap(glosses[0], width, initial=f"    {number}. ", subsequent="       ")
        lines.extend(_style_sense_number(sense_lines, number, style))
        for gloss in glosses[1:]:
            lines.extend(_wrap_value(gloss, width, "       "))
    else:
        lines.extend(_style_sense_number([f"    {number}."], number, style))
    if "tags" in fields:
        tagged = _wrap_labeled("tags", sense.tags, width, "       ")
        lines.extend(_style_label(tagged, indent="       ", label="tags", style=style))
    if "topics" in fields:
        topics = _wrap_labeled("topics", sense.topics, width, "       ")
        lines.extend(_style_label(topics, indent="       ", label="topics", style=style))
    if "examples" in fields and sense.examples:
        _append_block(lines, _render_examples(sense, width, style))
    if "synonyms" in fields:
        synonyms = _wrap_labeled("synonyms", sense.synonyms, width, "       ", locale)
        lines.extend(_style_label(synonyms, indent="       ", label="synonyms", style=style))
    if "antonyms" in fields:
        antonyms = _wrap_labeled("antonyms", sense.antonyms, width, "       ", locale)
        lines.extend(_style_label(antonyms, indent="       ", label="antonyms", style=style))
    return lines


def _render_entry(
    entry: DictionaryEntry,
    fields: frozenset[str],
    width: int,
    number: int,
    detail: str,
    locale: str | None,
    style: TerminalStyle,
) -> list[str]:
    pos = entry.pos or "entry"
    lines = [f"  {style.bold_magenta(pos)}"]
    if "etymology" in fields and entry.etymology:
        _append_block(lines, _render_etymology(entry.etymology, width, style))
    if "pronunciations" in fields and entry.pronunciations:
        if detail == "standard":
            block = ["    pronunciation: "]
            block[0] += _format_pronunciation(entry.pronunciations[0], locale)
            block.extend(
                f"      {_format_pronunciation(value, locale)}"
                for value in entry.pronunciations[1:]
            )
            block = _style_label(block, indent="    ", label="pronunciation", style=style)
        else:
            block = [f"    {style.cyan('pronunciations')}"]
            block.extend(
                f"      {_format_pronunciation(value, locale)}" for value in entry.pronunciations
            )
        _append_block(lines, block)
    if "forms" in fields and entry.forms:
        if detail == "standard":
            block = [f"    forms: {_format_form(entry.forms[0], locale)}"]
            block.extend(f"      {_format_form(value, locale)}" for value in entry.forms[1:])
            block = _style_label(block, indent="    ", label="forms", style=style)
        else:
            block = [f"    {style.cyan('forms')}"]
            block.extend(f"      {_format_form(value, locale)}" for value in entry.forms)
        _append_block(lines, block)
    for sense in entry.senses:
        _append_block(lines, _render_sense(sense, number, fields, width, locale, style))
        number += 1
    return lines


def _render_compact(
    entries: Sequence[DictionaryEntry],
    fields: frozenset[str],
    width: int,
    locale: str | None,
    style: TerminalStyle,
) -> list[str]:
    lines: list[str] = []
    number = 1
    for entry in entries:
        pos = entry.pos or "entry"
        lines.append(f"  {style.bold_magenta(pos)}")
        if not entry.senses:
            continue
        if fields:
            for sense in entry.senses:
                _append_block(lines, _render_sense(sense, number, fields, width, locale, style))
                number += 1
        else:
            gloss = next((value for value in entry.senses[0].glosses if value), "")
            additional = len(entry.senses) - 1
            suffix = f"  +{additional} sense" if additional == 1 else f"  +{additional} senses"
            lines.append(f"    {gloss}{suffix if additional else ''}")
            number += len(entry.senses)
    return lines


def render_dictionary_entries(
    word: str,
    entries: Sequence[DictionaryEntry],
    *,
    options: DictionaryRenderOptions,
    detail: str = "standard",
) -> str:
    style = TerminalStyle(options.color)
    lines = [style.bold_cyan(word)]
    if not entries:
        lines.append(f"  {style.yellow('no dictionary entries found')}")
        return "\n".join(lines)
    if detail == "compact":
        body = _render_compact(entries, options.fields, options.width, options.locale, style)
    else:
        body = []
        number = 1
        for entry in entries:
            _append_block(
                body,
                _render_entry(
                    entry,
                    options.fields,
                    options.width,
                    number,
                    detail,
                    options.locale,
                    style,
                ),
            )
            number += len(entry.senses)
    lines.extend(body)
    return "\n".join(lines)


__all__ = [
    "DETAIL_FIELDS",
    "DICTIONARY_FIELDS",
    "DictionaryRenderOptions",
    "filter_dictionary_entries",
    "normalize_dictionary_field",
    "normalize_pos",
    "parse_dictionary_fields",
    "parse_pos_selectors",
    "render_dictionary_entries",
    "resolve_dictionary_fields",
    "resolve_pos_filters",
    "split_csv",
    "terminal_render_width",
]
