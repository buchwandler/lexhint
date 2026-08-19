from pathlib import Path

from lexhint import Dictionary, Lexicon, build_dictionary

FIXTURE = Path(__file__).parent / "fixtures" / "kaikki-mini.jsonl"


def span(text: str, target: str) -> tuple[int, int]:
    start = text.index(target)
    return start, start + len(target)


def build(tmp_path: Path) -> Dictionary:
    lexicon = Lexicon.from_words(["the", "scale", "compiler", "chord", "is", "chat"])
    path, stats = build_dictionary("en", FIXTURE, lexicon=lexicon, output=tmp_path / "en.sqlite3")
    assert stats.scanned_entries == 5
    assert stats.matched_entries == 3
    assert stats.words == 3
    assert stats.senses == 5
    return Dictionary.from_path(path, language="en")


def test_dictionary_parses_senses_and_topics(tmp_path: Path) -> None:
    dictionary = build(tmp_path)
    senses = dictionary.senses("scale")
    assert len(senses) == 2
    assert "music" in dictionary.topics("scale")
    assert "metrology" in dictionary.topics("scale")
    assert "computing" in dictionary.topics("compiler")
    assert not dictionary.contains("banana")


def test_music_context_is_dictionary_derived(tmp_path: Path) -> None:
    dictionary = build(tmp_path)
    text = "The scale is Am."
    support = dictionary.supports(text, target=span(text, "Am"), topic="music")
    assert support is not None
    assert support.topic == "music"
    assert "scale" in [cue.casefold() for cue in support.cues]


def test_software_context_is_dictionary_derived(tmp_path: Path) -> None:
    dictionary = build(tmp_path)
    text = "The compiler is 8.3.2."
    support = dictionary.supports(text, target=span(text, "8.3.2"), topic="computing")
    assert support is not None
    assert "compiler" in [cue.casefold() for cue in support.cues]


def test_candidate_does_not_validate_itself(tmp_path: Path) -> None:
    dictionary = build(tmp_path)
    text = "scale"
    assert dictionary.supports(text, target=span(text, "scale"), topic="music") is None


def test_unrelated_context_fails_closed(tmp_path: Path) -> None:
    dictionary = build(tmp_path)
    text = "Am I late?"
    assert dictionary.supports(text, target=span(text, "Am"), topic="music") is None
