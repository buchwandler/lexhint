import gzip
from pathlib import Path

from lexhint import Lexicon, build_dictionary
from lexhint.builder import iter_wiktextract_entries


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
    build_dictionary(
        "en",
        source,
        lexicon=Lexicon.from_words(["scale"]),
        output=tmp_path / "en.sqlite3",
        progress=updates.append,
    )
    assert updates
    assert updates[-1].scanned_entries == 1
    assert updates[-1].words == 1
