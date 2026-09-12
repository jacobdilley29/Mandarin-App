"""Restore learner progress from a JSON export.

    python -m scripts.import_progress progress.json              # merge (default)
    python -m scripts.import_progress progress.json --replace    # true restore

A safety snapshot of the current progress.db is taken before anything is
written, so a mistaken import is itself recoverable.
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
from pathlib import Path

from app import backup


def _load(path: Path) -> dict:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Import learner progress from JSON.")
    parser.add_argument("file", type=Path, help="Export file (.json or .json.gz).")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Wipe existing progress first (a true restore). Default is to merge.",
    )
    parser.add_argument(
        "--no-safety-backup",
        action="store_true",
        help="Skip the automatic pre-import snapshot. Not recommended.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")

    payload = _load(args.file)
    counts = backup.import_progress(
        payload,
        mode="replace" if args.replace else "merge",
        safety_backup=not args.no_safety_backup,
    )
    for table, n in counts.items():
        if n:
            print(f"  {table:<16} {n}")
    print(f"Imported {sum(counts.values())} rows ({'replace' if args.replace else 'merge'}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
