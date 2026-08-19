from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from lexhint.download import cached_wordlist_path, fetch_wordlist


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("languages", nargs="+")
    args = parser.parse_args()
    destination = Path(__file__).resolve().parents[1] / "lexhint" / "data" / "words"
    destination.mkdir(parents=True, exist_ok=True)
    for language in args.languages:
        source = cached_wordlist_path(language)
        if not source.exists():
            source = fetch_wordlist(language)
        target = destination / f"{language}.txt.gz"
        shutil.copy2(source, target)
        print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
