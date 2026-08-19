import io
import json

from lexhint.download import (
    _FREQUENCYWORDS_REVISION,
    KAIKKI_RAW_URL,
    cached_dictionary_path,
    cached_wordlist_metadata_path,
    cached_wordlist_path,
    fetch_wordlist,
    wordlist_source_url,
)


def test_cache_paths_can_be_overridden(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LEXHINT_CACHE_DIR", str(tmp_path))
    assert cached_wordlist_path("en") == tmp_path / "words" / "en.txt.gz"
    assert cached_wordlist_metadata_path("en") == tmp_path / "words" / "en.metadata.json"
    assert cached_dictionary_path("en") == tmp_path / "dictionaries" / "en.sqlite3"


def test_kaikki_url_is_explicit() -> None:
    assert KAIKKI_RAW_URL.endswith("raw-wiktextract-data.jsonl.gz")


def test_wordlist_source_is_pinned() -> None:
    url = wordlist_source_url("en")
    assert _FREQUENCYWORDS_REVISION in url
    assert "/master/" not in url


def test_wordlist_fetch_writes_provenance_and_reuses_valid_cache(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LEXHINT_CACHE_DIR", str(tmp_path))
    source = "\n".join(f"word{i} {50_000 - i}" for i in range(45_000)) + "\n"
    requests = []

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    def fake_urlopen(request, *, timeout):
        requests.append((request, timeout))
        return Response(source.encode("utf-8"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    path = fetch_wordlist("en")
    metadata = json.loads(cached_wordlist_metadata_path("en").read_text(encoding="utf-8"))

    assert path.exists()
    assert metadata["language"] == "en"
    assert metadata["source_revision"] == _FREQUENCYWORDS_REVISION
    assert metadata["word_count"] == 45_000
    assert len(metadata["normalized_sha256"]) == 64
    assert requests[0][0].get_header("User-agent").startswith("lexhint/")

    def fail_urlopen(*_args, **_kwargs):
        raise AssertionError("valid cached word list should be reused")

    monkeypatch.setattr("urllib.request.urlopen", fail_urlopen)
    assert fetch_wordlist("en") == path


def test_wordlist_force_refresh_is_explicit(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LEXHINT_CACHE_DIR", str(tmp_path))
    source = "\n".join(f"word{i} {50_000 - i}" for i in range(45_000)) + "\n"

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    calls = 0

    def fake_urlopen(_request, *, timeout):
        nonlocal calls
        calls += 1
        return Response(source.encode("utf-8"))

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    fetch_wordlist("en")
    fetch_wordlist("en", force=True)
    assert calls == 2
