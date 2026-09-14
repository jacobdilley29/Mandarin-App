"""Run a backup now: snapshot + JSON export + prune.

This is what the cron container invokes nightly, and what `make backup` runs by
hand. Deliberately independent of the web app — it talks to progress.db
directly, so a backup is still possible when the server won't start.

    python -m scripts.backup [--retention-days N]
"""

from __future__ import annotations

import argparse
import logging
import sys

from app import backup
from app.config import get_settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Back up learner progress.")
    parser.add_argument(
        "--retention-days",
        type=int,
        default=None,
        help="Override the rolling window (default: BACKUP_RETENTION_DAYS, 30).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")

    settings = get_settings()
    if not settings.progress_db_path.is_file():
        print(
            f"No progress database at {settings.progress_db_path} — nothing to back up yet.",
            file=sys.stderr,
        )
        return 0

    result = backup.run_backup(retention_days=args.retention_days)
    print(f"snapshot : {result['snapshot']}")
    print(f"export   : {result['export']}")
    print(f"pruned   : {len(result['pruned'])} file(s) older than {result['retention_days']} days")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
