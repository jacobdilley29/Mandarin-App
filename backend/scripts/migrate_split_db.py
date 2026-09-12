"""Split a pre-existing data/mandarin.db into content.db + progress.db.

The app runs this automatically on startup; this script exists so the migration
can also be run (and its output inspected) by hand before starting the app.

    python -m scripts.migrate_split_db
"""

from __future__ import annotations

import logging

from app.config import get_settings
from app.migrate import split_legacy_db


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
    settings = get_settings()

    counts = split_legacy_db()
    if counts is None:
        print(f"Nothing to migrate (no {settings.legacy_db_path}, or already split).")
        return 0

    for table, n in sorted(counts.items()):
        print(f"  {table:<16} {n}")
    print(f"\nSplit into:\n  {settings.content_db_path}\n  {settings.progress_db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
