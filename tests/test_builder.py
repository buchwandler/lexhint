import gzip
from pathlib import Path

from lexhint.builder import iter_wiktextract_entries


def test_iter_wiktextract_entries_reads_gzip(tmp_path: Path) -> None:
    path = tmp_path / "mini.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write('{"word":"scale","lang_code":"en","senses":[]}\n')
    entries = list(iter_wiktextract_entries(path))
    assert entries == [{"word": "scale", "lang_code": "en", "senses": []}]
