import pytest

import lexhint
from lexhint import LexicalSegment, Lexicon


def test_membership_and_rank() -> None:
    lexicon = Lexicon.from_words(["the", "chat", "stack", "overflow"])
    assert "chat" in lexicon
    assert lexicon.contains("CHAT")
    assert lexicon.rank("chat") == 2
    assert lexicon.rank("gpt") is None


def test_top_level_api_is_runtime_only() -> None:
    assert "LexicalSegment" in lexhint.__all__
    assert "TopicEvidence" in lexhint.__all__
    assert "build_dictionary" not in lexhint.__all__
    assert not hasattr(lexhint, "build_dictionary")


def test_segment_keeps_unknown_initialism_together() -> None:
    lexicon = Lexicon.from_words(["the", "chat", "hat", "at"])
    assert lexicon.segment("chatgpt") == (
        LexicalSegment("chat", in_lexicon=True, frequency_rank=2),
        LexicalSegment("gpt", in_lexicon=False),
    )


def test_segment_two_known_words() -> None:
    lexicon = Lexicon.from_words(["stack", "overflow", "over", "flow"])
    result = lexicon.segment("stackoverflow")
    assert [part.text for part in result] == ["stack", "overflow"]
    assert all(part.in_lexicon for part in result)


def test_segment_ignores_obscure_two_letter_match_inside_initialism() -> None:
    lexicon = Lexicon.from_words(["the", "chat"] + [f"word{i}" for i in range(2500)] + ["gp"])
    result = lexicon.segment("chatgpt")
    assert result == (
        LexicalSegment("chat", in_lexicon=True, frequency_rank=2),
        LexicalSegment("gpt", in_lexicon=False),
    )


@pytest.fixture
def domain_label_lexicon() -> Lexicon:
    return Lexicon.from_words(
        [
            "chat",
            "stack",
            "overflow",
            "github",
            "gitlab",
            "python",
            "numpy",
            "pytorch",
            "microsoft",
            "reddit",
            "youtube",
            "linkedin",
            "whatsapp",
            "tiktok",
            "huggingface",
            "openai",
            "webmail",
            "notebook",
            "therapist",
            "notable",
            "therefore",
            "web",
            "mp",
            "foo",
            "bar",
            "ai",
            "io",
            "it",
            "de",
            "us",
            "uk",
            "tv",
            "app",
            "dev",
        ]
    )


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("chatgpt", [("chat", True), ("gpt", False)]),
        ("stackoverflow", [("stack", True), ("overflow", True)]),
        ("github", [("github", True)]),
        ("openai", [("openai", True)]),
        ("gpt4", [("gpt4", False)]),
        ("web3", [("web", True), ("3", False)]),
        ("mp3", [("mp", True), ("3", False)]),
        ("x86", [("x86", False)]),
        ("foo2bar", [("foo", True), ("2", False), ("bar", True)]),
        ("ai", [("ai", True)]),
        ("foo-bar", [("foo", True), ("-", False), ("bar", True)]),
        ("chat-gpt", [("chat", True), ("-gpt", False)]),
        ("café", [("café", False)]),
        ("xn--bcher-kva", [("xn--bcher-kva", False)]),
    ],
)
def test_domain_label_regression_corpus(
    domain_label_lexicon: Lexicon, label: str, expected: list[tuple[str, bool]]
) -> None:
    result = domain_label_lexicon.segment(label)
    assert [(item.text, item.in_lexicon) for item in result] == expected


def test_segment_does_not_parse_url_syntax(domain_label_lexicon: Lexicon) -> None:
    result = domain_label_lexicon.segment("chatgpt.com")
    assert [item.text for item in result] == ["chat", "gpt.com"]


def test_segment_normalizes_case_and_unicode() -> None:
    lexicon = Lexicon.from_words(["café"])
    assert lexicon.segment("CAFE\u0301") == (LexicalSegment("café", True, 1),)
