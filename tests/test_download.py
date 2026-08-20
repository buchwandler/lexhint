from pathlib import Path

from lexhint.download import cache_dir, cached_dictionary_path, package_version, user_agent


def test_cache_paths_use_dictionary_artifact(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LEXHINT_CACHE_DIR", str(tmp_path))
    assert cache_dir() == tmp_path
    assert cached_dictionary_path("EN-us") == tmp_path / "dictionaries" / "en.sqlite3"
    assert not (tmp_path / "words").exists()


def test_request_identity_is_available() -> None:
    assert package_version()
    assert user_agent().startswith("lexhint/")
