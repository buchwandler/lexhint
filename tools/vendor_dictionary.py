from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from lexhint.download import cached_dictionary_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("languages", nargs="+")
    args = parser.parse_args()
    destination = Path(__file__).resolve().parents[1] / "lexhint" / "data" / "dictionaries"
    destination.mkdir(parents=True, exist_ok=True)
    for language in args.languages:
        source = cached_dictionary_path(language)
        if not source.exists():
            raise SystemExit(f"dictionary not built: {source}")
        target = destination / f"{language}.sqlite3"
        shutil.copy2(source, target)
        print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
