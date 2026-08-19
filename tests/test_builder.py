import gzip
import sqlite3
from contextlib import closing
from pathlib import Path

from lexhint import build_dictionary
from lexhint.builder import iter_wiktextract_entries

FIXTURE = Path(__file__).parent / "fixtures" / "kaikki-mini.jsonl"


def test_iter_wiktextract_entries_reads_gzip(tmp_path: Path) -> None:
    path = tmp_path / "mini.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write('{"word":"scale","lang_code":"en","senses":[]}\n')
    entries = list(iter_wiktextract_entries(path))
    assert entries == [{"word": "scale", "lang_code": "en", "senses": []}]


def test_build_dictionary_reports_progress(tmp_path: Path) -> None:
    source = tmp_path / "mini.jsonl.gz"
    with gzip.open(source, "wt", encoding="utf-8") as handle:
        handle.write(
            '{"word":"scale","lang_code":"en","pos":"noun",'
            '"senses":[{"glosses":["a measuring instrument"],"topics":["metrology"]}]}\n'
        )
    updates = []
    _, stats = build_dictionary(
        "en",
        source,
        output=tmp_path / "en.sqlite3",
        progress=updates.append,
    )
    assert updates
    assert updates[-1].scanned_entries == 1
    assert updates[-1].kept_entries == 1
    assert updates[-1].words == 1
    assert stats.senses == 1


def test_fixture_build_is_independent_of_wordlist(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LEXHINT_CACHE_DIR", str(tmp_path / "empty-cache"))
    path, stats = build_dictionary("en", FIXTURE)
    assert path.exists()
    assert stats.kept_entries == 5
    assert not (tmp_path / "empty-cache" / "words" / "en.txt.gz").exists()

    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone() == ("4",)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(senses)")}
    assert columns == {"id", "word", "display_word", "pos", "glosses", "topics"}
    with closing(sqlite3.connect(path)) as connection:
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        assert metadata["coverage"] == "full"
        assert metadata["source_kind"] == "bulk"
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE name = 'lookups'"
        ).fetchone()
