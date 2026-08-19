from lexhint import Lexicon, Segment


def test_membership_and_rank() -> None:
    lexicon = Lexicon.from_words(["the", "chat", "stack", "overflow"])
    assert "chat" in lexicon
    assert lexicon.contains("CHAT")
    assert lexicon.rank("chat") == 2
    assert lexicon.rank("gpt") is None


def test_segment_keeps_unknown_initialism_together() -> None:
    lexicon = Lexicon.from_words(["the", "chat", "hat", "at"])
    assert lexicon.segment("chatgpt") == (
        Segment("chat", known=True, rank=2),
        Segment("gpt", known=False),
    )


def test_segment_two_known_words() -> None:
    lexicon = Lexicon.from_words(["stack", "overflow", "over", "flow"])
    result = lexicon.segment("stackoverflow")
    assert [part.text for part in result] == ["stack", "overflow"]
    assert all(part.known for part in result)
