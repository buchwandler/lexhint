from __future__ import annotations

from pathlib import Path

from lexhint import Lexicon, SemanticDomain
from lexhint.builder import build_dictionary

FIXTURE = Path(__file__).parent / "fixtures" / "kaikki-mini.jsonl"


def build(tmp_path: Path) -> Lexicon:
    path, _ = build_dictionary(
        "en",
        FIXTURE,
        output=tmp_path / "en.sqlite3",
        no_frequency=True,
    )
    return Lexicon.from_path(path)


def test_numeric_target_keeps_adjacent_cue_before_target(tmp_path: Path) -> None:
    lexicon = build(tmp_path)
    text = "compiler 8.3.2"
    target = (text.index("8.3.2"), len(text))

    evidence = lexicon.supports_domain(text, target=target, domain=SemanticDomain.COMPUTING)

    assert evidence is not None
    assert evidence.cues[0].text == "compiler"
    assert evidence.cues[0].distance == 1


def test_numeric_target_keeps_adjacent_cue_after_target(tmp_path: Path) -> None:
    lexicon = build(tmp_path)
    text = "8.3.2 compiler"
    target = (0, text.index("compiler") - 1)

    evidence = lexicon.supports_domain(text, target=target, domain="computing")

    assert evidence is not None
    assert evidence.cues[0].text == "compiler"
    assert evidence.cues[0].distance == 1


def test_multiple_words_before_numeric_target_keep_lexical_distance(tmp_path: Path) -> None:
    lexicon = build(tmp_path)
    text = "The compiler is 8.3.2"
    target = (text.index("8.3.2"), len(text))

    evidence = lexicon.supports_domain(text, target=target, domain="computing")

    assert evidence is not None
    assert evidence.cues[0].text == "compiler"
    assert evidence.cues[0].distance == 2


def test_punctuation_only_target_keeps_adjacent_cue(tmp_path: Path) -> None:
    lexicon = build(tmp_path)
    text = "compiler: ???"
    target = (text.index("???"), len(text))

    evidence = lexicon.supports_domain(text, target=target, domain="computing")

    assert evidence is not None
    assert evidence.cues[0].text == "compiler"
    assert evidence.cues[0].distance == 1


def test_word_target_excludes_overlapping_token(tmp_path: Path) -> None:
    lexicon = build(tmp_path)
    text = "scale compiler"
    target = (text.index("compiler"), len(text))

    evidence = lexicon.supports_domain(text, target=target, domain="music")

    assert evidence is not None
    assert all(cue.text != "compiler" for cue in evidence.cues)
    assert evidence.cues[0].text == "scale"
    assert evidence.cues[0].distance == 1


def test_window_zero_has_no_context(tmp_path: Path) -> None:
    lexicon = build(tmp_path)
    text = "compiler 8.3.2"
    target = (text.index("8.3.2"), len(text))

    assert lexicon.context_domains(text, target=target, window=0) == ()


def test_virtual_boundary_at_text_edges_keeps_nearest_word(tmp_path: Path) -> None:
    lexicon = build(tmp_path)

    before = lexicon.supports_domain("8.3.2 compiler", target=(0, 5), domain="computing")
    after_text = "compiler 8.3.2"
    after = lexicon.supports_domain(
        after_text, target=(len(after_text), len(after_text)), domain="computing"
    )

    assert before is not None
    assert before.cues[0].distance == 1
    assert after is not None
    assert after.cues[0].distance == 1


def test_zero_length_target_inside_word_is_a_virtual_boundary(tmp_path: Path) -> None:
    lexicon = build(tmp_path)

    evidence = lexicon.context_domains("compiler", target=(1, 1))[0]

    assert evidence.cues[0].text == "compiler"
    assert evidence.cues[0].distance == 1
