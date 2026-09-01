from __future__ import annotations

import os
import re

import pytest

from lexhint.models import DictionaryEntry, Example, Form, Pronunciation, Sense
from lexhint.render import (
    DictionaryRenderOptions,
    filter_dictionary_entries,
    normalize_pos,
    render_dictionary_entries,
    resolve_dictionary_fields,
    resolve_pos_filters,
    terminal_render_width,
)


def test_dictionary_field_resolution_supports_overlays_aliases_and_groups() -> None:
    assert resolve_dictionary_fields("compact", show=["example,tag"]) == {
        "examples",
        "tags",
    }
    assert resolve_dictionary_fields("full", hide=["entry", "relations"]) == {
        "tags",
        "topics",
        "examples",
    }


def test_dictionary_field_resolution_rejects_unknown_and_conflicting_fields() -> None:
    with pytest.raises(ValueError, match="unknown dictionary field 'examplez'"):
        resolve_dictionary_fields("full", show=["examplez"])
    with pytest.raises(ValueError, match="present in both"):
        resolve_dictionary_fields("full", show=["example"], hide=["examples"])


def test_pos_filters_normalize_and_preserve_entry_order() -> None:
    entries = (
        DictionaryEntry("word", "noun", (Sense(glosses=("one",)),)),
        DictionaryEntry("word", "Proper Noun", (Sense(glosses=("two",)),)),
        DictionaryEntry("word", "verb", (Sense(glosses=("three",)),)),
    )
    include, exclude = resolve_pos_filters(["NOUN, proper_noun"], ["verb"])
    assert include == {"noun", "proper noun"}
    assert exclude == {"verb"}
    filtered = filter_dictionary_entries(entries, include=include, exclude=exclude)
    assert tuple(entry.pos for entry in filtered) == ("noun", "Proper Noun")
    assert normalize_pos("  Proper-Noun ") == "proper noun"

    with pytest.raises(ValueError, match="present in both"):
        resolve_pos_filters(["noun"], ["NOUN"])


def test_renderer_preserves_hierarchy_and_wraps_rich_fields() -> None:
    entry = DictionaryEntry(
        "love",
        "noun",
        (
            Sense(
                glosses=(
                    "A very long definition that should wrap across multiple readable lines.",
                    "A second gloss belonging to the same sense.",
                ),
                tags=("uncountable",),
                topics=("sports",),
                examples=(
                    Example(
                        "A long example that should remain nested below its sense.",
                        "Ein langes Beispiel.",
                    ),
                ),
                synonyms=("affection",),
                antonyms=("hate",),
            ),
        ),
        forms=(Form("loves", ("plural",)),),
        pronunciations=(Pronunciation("/lʌv/", ("US",)),),
        etymology="From Middle English love.\n\nCognates\nCognate with Scots luve.",
    )
    options = DictionaryRenderOptions(
        fields=resolve_dictionary_fields("full"),
        width=60,
    )

    output = render_dictionary_entries("love", (entry,), options=options, detail="full")

    assert "love\n  noun" in output
    assert "    etymology\n      From Middle English love." in output
    assert "      Cognates" in output
    assert "    1. A very long definition" in output
    assert "       examples\n         - A long example" in output
    assert "           translation: Ein langes Beispiel." in output
    assert "       synonyms: affection" in output
    assert "    forms\n      loves [plural]" in output
    assert "    pronunciations\n      [lʌv] [US]" in output
    assert all(len(line) <= 60 for line in output.splitlines())


def test_terminal_width_is_capped_and_explicit_width_is_validated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "lexhint.render.shutil.get_terminal_size",
        lambda fallback: os.terminal_size((250, 24)),
    )
    assert terminal_render_width() == 100
    assert terminal_render_width(120) == 120
    with pytest.raises(ValueError, match="between 40 and 240"):
        terminal_render_width(39)


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(value: str) -> str:
    return ANSI_RE.sub("", value)


def _color_test_entry() -> DictionaryEntry:
    return DictionaryEntry(
        "love",
        "noun",
        (
            Sense(
                glosses=("A strong feeling of affection.",),
                tags=("uncountable",),
                topics=("sports",),
                examples=(Example("Their love grew over time.", "Ihre Liebe wuchs."),),
                synonyms=("affection",),
                antonyms=("hate",),
            ),
        ),
        forms=(Form("loves", ("plural",)),),
        pronunciations=(Pronunciation("/lʌv/", ("US",)),),
        etymology="From Middle English love.",
    )


@pytest.mark.parametrize("detail", ["compact", "standard", "full"])
def test_colored_dictionary_output_matches_plain_and_fits_visible_width(detail: str) -> None:
    entry = _color_test_entry()
    fields = resolve_dictionary_fields(detail)
    plain = render_dictionary_entries(
        "love",
        (entry,),
        options=DictionaryRenderOptions(fields=fields, width=60, color=False),
        detail=detail,
    )
    colored = render_dictionary_entries(
        "love",
        (entry,),
        options=DictionaryRenderOptions(fields=fields, width=60, color=True),
        detail=detail,
    )

    assert "\x1b[" in colored
    assert strip_ansi(colored) == plain
    assert all(len(strip_ansi(line)) <= 60 for line in colored.splitlines())


def test_colored_dictionary_output_uses_semantic_styles() -> None:
    entry = _color_test_entry()
    colored = render_dictionary_entries(
        "love",
        (entry,),
        options=DictionaryRenderOptions(
            fields=resolve_dictionary_fields("full"), width=60, color=True
        ),
        detail="full",
    )

    assert "\033[1;36mlove\033[0m" in colored
    assert "\033[1;35mnoun\033[0m" in colored
    assert "\033[36m1.\033[0m" in colored
    assert "\033[2;36mtags:\033[0m" in colored
    assert "\033[2;36mtranslation:\033[0m" in colored
    assert "\033[36metymology\033[0m" in colored
    assert "\033[36mexamples\033[0m" in colored


def test_renderer_labels_quotation_kind() -> None:
    entry = DictionaryEntry(
        "love",
        "noun",
        (Sense(glosses=("A feeling.",), examples=(Example("A quote.", kind="quotation"),)),),
    )
    output = render_dictionary_entries(
        "love",
        (entry,),
        options=DictionaryRenderOptions(fields=resolve_dictionary_fields("full"), width=60),
        detail="full",
    )
    assert "- [quotation] A quote." in output


def test_renderer_deduplicates_equivalent_ipa_delimiters() -> None:
    entry = DictionaryEntry(
        "love",
        "noun",
        (Sense(glosses=("A feeling.",)),),
        pronunciations=(
            Pronunciation("/lʌv/", ("US",)),
            Pronunciation("[lʌv]", ("US",)),
        ),
    )
    output = render_dictionary_entries(
        "love",
        (entry,),
        options=DictionaryRenderOptions(fields=resolve_dictionary_fields("full"), width=60),
        detail="full",
    )
    assert output.count("[lʌv] [US]") == 1
    assert "/lʌv/" not in output
