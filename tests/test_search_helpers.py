from __future__ import annotations

import pytest

from lexhint.search import (
    edit_distance,
    glob_literal_prefix,
    regex_literal_prefix,
    search_tokens,
    weighted_term_score,
    word_ngrams,
)


def test_search_tokens_are_unicode_normalized_and_ordered() -> None:
    assert search_tokens("LARGE, fi\u0065\u0301line's well-known") == (
        "large",
        "fi\u00e9line's",
        "well-known",
    )


def test_word_ngrams_include_boundaries_and_are_unique() -> None:
    grams = word_ngrams("defer")
    assert "^d" in grams
    assert "^de" in grams
    assert "def" in grams
    assert "er$" in grams
    assert len(grams) == len(set(grams))
    assert word_ngrams("ab") == ("^a", "ab", "b$")


def test_edit_distance_supports_adjacent_transposition_and_bounds() -> None:
    assert edit_distance("teh", "the") == 1
    assert edit_distance("kitten", "sitting") == 3
    assert edit_distance("kitten", "sitting", max_distance=1) == 2
    assert edit_distance("same", "same", max_distance=0) == 0
    with pytest.raises(ValueError):
        edit_distance("a", "b", max_distance=-1)


def test_literal_prefix_helpers() -> None:
    assert glob_literal_prefix("comp*") == "comp"
    assert glob_literal_prefix("*tion") == ""
    assert glob_literal_prefix("literal") == "literal"
    assert regex_literal_prefix("^comp.*er$") == "comp"
    assert regex_literal_prefix("colou?r") == ""
    assert regex_literal_prefix("^foo\\.bar$") == "foo.bar"


def test_weighted_term_score_caps_repetition() -> None:
    assert weighted_term_score("glosses", 1) == 4.0
    assert weighted_term_score("glosses", 20) == 12.0
