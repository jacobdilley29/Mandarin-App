"""One-time migration from the pre-split single-file database.

Earlier versions kept curriculum and learner progress together in
``data/mandarin.db``. Spec §7 requires them apart, so on first startup after
the upgrade this module copies each table into the file it now belongs to:

    mandarin.db ──┬─► content.db    (dictionary, vocab, grammar, units, lessons, …)
                  └─► progress.db   (srs_cards, review_log, settings, …)

The original file is renamed, never deleted — if anything about the split looks
wrong, ``mandarin.db.pre-split.bak`` is still sitting there untouched.

Idempotent: once content.db and progress.db exist, this is a no-op.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
from pathlib import Path

from .config import get_settings

log = logging.getLogger(__name__)

LEGACY_BACKUP_SUFFIX = ".pre-split.bak"


def split_legacy_db() -> dict[str, int] | None:
    """Split data/mandarin.db into content.db + progress.db.

    Returns per-table row counts when a migration ran, or None when there was
    nothing to do (no legacy file, or the split already happened).
    """
    settings = get_settings()
    legacy = settings.legacy_db_path

    if not legacy.is_file():
        return None
    if settings.content_db_path.exists() or settings.progress_db_path.exists():
        # Already split (or a fresh install that has since run). Leave the
        # legacy file alone rather than risk overwriting newer data.
        log.warning(
            "Found %s alongside an already-split layout — leaving it untouched. "
            "Delete it by hand once you're satisfied the split data is correct.",
            legacy,
        )
        return None

    log.info("Migrating %s to the split content/progress layout…", legacy)

    # Local imports: db imports this module, so keep the dependency one-way.
    from .db import (
        CONTENT_SCHEMA_PATH,
        CONTENT_TABLES,
        PROGRESS_SCHEMA_PATH,
        PROGRESS_TABLES,
        connect_single,
    )

    counts: dict[str, int] = {}
    src = connect_single(legacy)
    try:
        existing = {
            r["name"]
            for r in src.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        counts |= _copy_into(
            src, settings.content_db_path, CONTENT_SCHEMA_PATH, CONTENT_TABLES, existing
        )
        counts |= _copy_into(
            src,
            settings.progress_db_path,
            PROGRESS_SCHEMA_PATH,
            PROGRESS_TABLES,
            existing,
        )
    finally:
        src.close()

    backup = legacy.with_name(legacy.name + LEGACY_BACKUP_SUFFIX)
    shutil.move(str(legacy), str(backup))
    # WAL sidecars belong to the old file; move them so they can't be replayed.
    for sidecar in ("-wal", "-shm"):
        stray = legacy.with_name(legacy.name + sidecar)
        if stray.exists():
            shutil.move(str(stray), str(backup.with_name(backup.name + sidecar)))

    log.info(
        "Migration complete: %s. Original preserved at %s",
        ", ".join(f"{t}={n}" for t, n in sorted(counts.items()) if n),
        backup,
    )
    return counts


def _copy_into(
    src: sqlite3.Connection,
    dest_path: Path,
    schema_path: Path,
    tables: tuple[str, ...],
    existing: set[str],
) -> dict[str, int]:
    """Create dest from its schema, then copy the named tables across."""
    from .db import connect_single

    dest = connect_single(dest_path)
    try:
        dest.executescript(schema_path.read_text(encoding="utf-8"))
        # The schema seeds a default settings row; drop it so the learner's own
        # row copies across cleanly rather than colliding with the singleton.
        if "settings" in tables:
            dest.execute("DELETE FROM settings")

        counts: dict[str, int] = {}
        for table in tables:
            if table not in existing:
                counts[table] = 0
                continue
            rows = src.execute(f"SELECT * FROM {table}").fetchall()  # noqa: S608
            if not rows:
                counts[table] = 0
                continue
            cols = rows[0].keys()
            placeholders = ", ".join("?" * len(cols))
            collist = ", ".join(f'"{c}"' for c in cols)
            dest.executemany(
                f'INSERT OR REPLACE INTO "{table}" ({collist}) VALUES ({placeholders})',  # noqa: S608
                [tuple(r) for r in rows],
            )
            counts[table] = len(rows)
        # Re-seed the settings singleton if the source had none.
        if "settings" in tables:
            dest.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
        dest.commit()
        return counts
    finally:
        dest.close()
