from __future__ import annotations

import io
import urllib.error

import pytest

from lexhint import kaikki


def response(payload: str) -> io.BytesIO:
    return io.BytesIO(payload.encode("utf-8"))


def test_kaikki_word_url_preserves_case_and_encodes_path() -> None:
    assert kaikki.kaikki_word_url("compiler").endswith("/meaning/c/co/compiler.jsonl")
    assert kaikki.kaikki_word_url("WinPE").endswith("/meaning/W/Wi/WinPE.jsonl")
    assert kaikki.kaikki_word_url("principal boy").endswith("/meaning/p/pr/principal%20boy.jsonl")
    assert "/%C3%BE/%C3%BEe/%C3%BEekking.jsonl" in kaikki.kaikki_word_url("þekking")


def test_word_entries_stream_matching_jsonl(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[object, float]] = []

    def fake_urlopen(request: object, timeout: float) -> io.BytesIO:
        calls.append((request, timeout))
        return response('{"word":"compiler","lang_code":"en","senses":[]}\n')

    monkeypatch.setattr(kaikki.urllib.request, "urlopen", fake_urlopen)
    assert tuple(kaikki.iter_word_entries("compiler", timeout=12)) == (
        {"word": "compiler", "lang_code": "en", "senses": []},
    )
    assert calls[0][1] == 12
    assert calls[0][0].headers["User-agent"] == kaikki.USER_AGENT  # type: ignore[union-attr]


def test_word_entries_classifies_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: object, timeout: float) -> object:
        raise urllib.error.HTTPError("url", 404, "missing", {}, None)

    monkeypatch.setattr(kaikki.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(kaikki.DictionaryWordNotFound):
        tuple(kaikki.iter_word_entries("missing"))


def test_word_entries_classifies_transient_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(request: object, timeout: float) -> object:
        raise OSError("offline")

    monkeypatch.setattr(kaikki.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(kaikki.DictionaryFetchError, match="offline"):
        tuple(kaikki.iter_word_entries("compiler"))


def test_word_entries_rejects_invalid_jsonl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(kaikki.urllib.request, "urlopen", lambda request, timeout: response("{"))
    with pytest.raises(kaikki.DictionaryFetchError, match="invalid Kaikki JSONL"):
        tuple(kaikki.iter_word_entries("compiler"))
