from lexhint.download import KAIKKI_RAW_URL, cached_dictionary_path, cached_wordlist_path


def test_cache_paths_can_be_overridden(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LEXHINT_CACHE_DIR", str(tmp_path))
    assert cached_wordlist_path("en") == tmp_path / "words" / "en.txt.gz"
    assert cached_dictionary_path("en") == tmp_path / "dictionaries" / "en.sqlite3"


def test_kaikki_url_is_explicit() -> None:
    assert KAIKKI_RAW_URL.endswith("raw-wiktextract-data.jsonl.gz")
