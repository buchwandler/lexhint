from pathlib import Path

import lexhint.download as download
from lexhint.download import cache_dir, cached_dictionary_path, package_version, user_agent


def test_cache_paths_use_dictionary_artifact(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LEXHINT_CACHE_DIR", str(tmp_path))
    assert cache_dir() == tmp_path
    assert cached_dictionary_path("EN-us") == tmp_path / "dictionaries" / "en.sqlite3"
    assert not (tmp_path / "words").exists()


def test_request_identity_is_available() -> None:
    assert package_version()
    assert user_agent().startswith("lexhint/")


def test_cache_dir_uses_xdg_fallback(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("LEXHINT_CACHE_DIR", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert download.cache_dir() == tmp_path / "lexhint"


def test_data_dir_uses_explicit_value(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LEXHINT_DATA_DIR", str(tmp_path))
    assert download.data_dir() == tmp_path


def test_request_adds_accept_and_token_headers(monkeypatch) -> None:
    captured = {}
    sentinel = object()

    def fake_urlopen(request, timeout):
        captured["headers"] = dict(request.header_items())
        captured["timeout"] = timeout
        return sentinel

    monkeypatch.setattr(download.urllib.request, "urlopen", fake_urlopen)
    assert (
        download.request(
            "https://example.test", accept="application/json", token="secret", timeout=4
        )
        is sentinel
    )
    assert captured == {
        "headers": {
            "Accept": "application/json",
            "Authorization": "Bearer secret",
            "User-agent": download.user_agent(),
        },
        "timeout": 4,
    }


def test_package_version_falls_back_when_distribution_is_missing(monkeypatch) -> None:
    def missing(_name: str) -> str:
        raise download.PackageNotFoundError("lexhint")

    monkeypatch.setattr(download, "version", missing)
    assert download.package_version() == "0+unknown"
