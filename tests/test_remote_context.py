from __future__ import annotations

from pathlib import Path

import pytest

from lexhint import Dictionary, DictionaryOfflineError
from lexhint import dictionary as dictionary_module


def semantic_entry(word: str, topic: str) -> dict[str, object]:
    return {
        "word": word,
        "lang_code": "en",
        "pos": "noun",
        "senses": [{"glosses": [word], "topics": [topic]}],
    }


def test_python_dictionary_is_local_only_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "en.sqlite3"
    dictionary = Dictionary("en", path=path, fetch_missing=True)
    monkeypatch.setattr(
        dictionary_module,
        "fetch_word_entries",
        lambda word, *, timeout: pytest.fail("local-only dictionary must not fetch"),
    )
    dictionary.fetch_missing = False
    assert dictionary.senses("compiler") == ()


def test_remote_context_fetches_only_nearby_non_target_tokens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "en.sqlite3"
    calls: list[str] = []

    def fake_fetch(word: str, *, timeout: float) -> tuple[dict[str, object], ...]:
        calls.append(word)
        if word == "compiler":
            return (semantic_entry(word, "computing"),)
        return ()

    monkeypatch.setattr(dictionary_module, "fetch_word_entries", fake_fetch)
    dictionary = Dictionary("en", path=path, fetch_missing=True)
    text = "scale compiler"
    support = dictionary.supports(text, target=(0, len("scale")), topic="computing")
    assert support is not None
    assert calls == ["compiler"]


def test_target_is_not_fetched_as_self_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "en.sqlite3"
    calls: list[str] = []

    def fake_fetch(word: str, *, timeout: float) -> tuple[dict[str, object], ...]:
        calls.append(word)
        return (semantic_entry(word, "music"),)

    monkeypatch.setattr(dictionary_module, "fetch_word_entries", fake_fetch)
    dictionary = Dictionary("en", path=path, fetch_missing=True)
    text = "scale"
    assert dictionary.supports(text, target=(0, len(text)), topic="music") is None
    assert calls == []


def test_offline_missing_word_is_controlled(tmp_path: Path) -> None:
    with pytest.raises(DictionaryOfflineError, match="not cached"):
        Dictionary("en", path=tmp_path / "en.sqlite3", offline=True)
