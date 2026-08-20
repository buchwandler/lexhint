import gzip
import sqlite3
from contextlib import closing
from pathlib import Path

from lexhint.builder import build_dictionary, iter_wiktextract_entries

FIXTURE = Path(__file__).parent / "fixtures" / "kaikki-mini.jsonl"


def test_iter_wiktextract_entries_reads_gzip(tmp_path: Path) -> None:
    path = tmp_path / "mini.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write('{"word":"scale","lang_code":"en","senses":[]}\n')
    assert list(iter_wiktextract_entries(path)) == [
        {"word": "scale", "lang_code": "en", "senses": []}
    ]


def test_build_dictionary_reports_progress(tmp_path: Path) -> None:
    source = tmp_path / "mini.jsonl.gz"
    with gzip.open(source, "wt", encoding="utf-8") as handle:
        handle.write(
            '{"word":"scale","lang_code":"en","pos":"noun",'
            '"senses":[{"glosses":["a measuring instrument"],"topics":["metrology"]}]}\n'
        )
    updates = []
    _, stats = build_dictionary(
        "en", source, output=tmp_path / "en.sqlite3", progress=updates.append
    )
    assert updates
    assert updates[-1].scanned_entries == 1
    assert updates[-1].kept_entries == 1
    assert updates[-1].words == 1
    assert stats.senses == 1


def test_build_contains_schema6_lexemes_and_no_wordlist(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("LEXHINT_CACHE_DIR", str(tmp_path / "empty-cache"))
    path, stats = build_dictionary("en", FIXTURE)
    assert path.exists()
    assert stats.kept_entries == 5
    assert stats.senses == 9
    assert not (tmp_path / "empty-cache" / "words").exists()

    with closing(sqlite3.connect(path)) as connection:
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    assert metadata["schema_version"] == "6"
    assert metadata["frequency_source"] == "none"
    assert {"entries", "senses", "sense_topics", "lookups", "lexemes"} <= tables
    assert metadata["extractor_schema_version"] == "6"


def test_build_enriches_existing_lexemes_only(tmp_path: Path) -> None:
    frequency = tmp_path / "frequency.txt"
    frequency.write_text("the 1000\ncompiler 100\nmadeupcorpusword 999999\n", encoding="utf-8")
    path, stats = build_dictionary(
        "en", FIXTURE, frequency_source=frequency, output=tmp_path / "en.sqlite3"
    )
    assert stats.frequency_rows == 3
    assert stats.frequency_matches == 1
    assert stats.frequency_total_tokens == 1001099
    with closing(sqlite3.connect(path)) as connection:
        compiler = connection.execute(
            "SELECT corpus_count, corpus_rank FROM lexemes WHERE word = 'compiler'"
        ).fetchone()
        missing = connection.execute(
            "SELECT 1 FROM lexemes WHERE word = 'madeupcorpusword'"
        ).fetchone()
    assert compiler == (100, 2)
    assert missing is None
