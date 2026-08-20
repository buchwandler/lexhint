from __future__ import annotations

import os

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
    assert "    pronunciations\n      /lʌv/ [US]" in output
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
