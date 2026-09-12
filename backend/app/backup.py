"""Backup, export and restore of learner progress (spec §7).

The previous incarnation of this app was lost because it had no backup story.
This module is the answer, and it is deliberately the *only* place backup logic
lives — the CLI scripts, the cron container and the admin API all call in here,
so there is one behaviour to reason about and one behaviour to test.

Two independent recovery paths, because a single one is a single point of failure:

  1. **Binary snapshot** — ``progress-YYYYMMDD-HHMMSS.db``, produced with SQLite's
     online backup API. Byte-exact, restores by copying the file back.
  2. **JSON export** — ``export-YYYYMMDD-HHMMSS.json.gz``, a plain-text dump of
     every progress table. Survives SQLite version changes, can be inspected and
     hand-edited, and is the thing to carry to a new machine.

What is NOT backed up, on purpose:

  * ``content.db`` — regenerates from the versioned ``content/*.json`` in git.
  * ``data/audio/`` — an edge-tts cache; it re-synthesises on demand.

Backing those up would multiply the size of every snapshot to protect data that
is already safe in git. The README says so explicitly so the omission is never
mistaken for an oversight.
"""

from __future__ import annotations

import gzip
import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .config import get_settings
from .db import PROGRESS_SCHEMA_VERSION, PROGRESS_TABLES, connect_single

log = logging.getLogger(__name__)

SNAPSHOT_PREFIX = "progress-"
SNAPSHOT_SUFFIX = ".db"
EXPORT_PREFIX = "export-"
EXPORT_SUFFIX = ".json.gz"

# YYYYMMDD-HHMMSS, optionally with a label suffix (e.g. "-pre-import").
# Matched strictly so pruning can never delete a file that merely happens to be
# sitting in the backups directory. Labelled snapshots match too, so they age
# out on the normal schedule instead of accumulating forever.
_STAMP_RE = re.compile(r"^\d{8}-\d{6}(?:-[a-z][a-z-]*)?$")

EXPORT_FORMAT = 1


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _stamp_of(path: Path, prefix: str, suffix: str) -> str | None:
    name = path.name
    if not (name.startswith(prefix) and name.endswith(suffix)):
        return None
    stamp = name[len(prefix) : -len(suffix)]
    return stamp if _STAMP_RE.match(stamp) else None


# ---------------------------------------------------------------------------
# Export / import
# ---------------------------------------------------------------------------
def export_progress(conn: sqlite3.Connection | None = None) -> dict:
    """Dump every progress table to a plain JSON-serialisable dict.

    Accepts either a connection with progress ATTACHed (the app's normal one) or
    None, in which case progress.db is opened directly — so an export still
    works when the app itself won't start.
    """
    own = conn is None
    if own:
        conn = connect_single(get_settings().progress_db_path)
    try:
        conn.row_factory = sqlite3.Row
        tables = {
            table: [dict(r) for r in conn.execute(f'SELECT * FROM "{table}"')]  # noqa: S608
            for table in PROGRESS_TABLES
        }
    finally:
        if own:
            conn.close()

    return {
        "format": EXPORT_FORMAT,
        "schema_version": PROGRESS_SCHEMA_VERSION,
        "app_version": __version__,
        "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tables": tables,
    }


def import_progress(
    payload: dict,
    mode: str = "merge",
    conn: sqlite3.Connection | None = None,
    safety_backup: bool = True,
) -> dict[str, int]:
    """Load a JSON export back into progress.db.

    mode="replace" clears each table first (a true restore); mode="merge"
    upserts rows on top of what's there (recovering a partial loss, or pulling
    in another machine's progress).

    Validated before anything is written, and — unless explicitly disabled — a
    safety snapshot is taken first, so a mistaken import is itself recoverable.
    """
    if mode not in ("merge", "replace"):
        raise ValueError(f"unknown import mode {mode!r} (expected 'merge' or 'replace')")

    fmt = payload.get("format")
    if fmt != EXPORT_FORMAT:
        raise ValueError(f"unsupported export format {fmt!r} (this build reads {EXPORT_FORMAT})")
    tables = payload.get("tables")
    if not isinstance(tables, dict):
        raise ValueError("export has no 'tables' object")
    unknown = set(tables) - set(PROGRESS_TABLES)
    if unknown:
        raise ValueError(f"export contains unknown tables: {', '.join(sorted(unknown))}")

    if safety_backup:
        snap = snapshot_progress(label="pre-import")
        log.info("Safety snapshot before import: %s", snap)

    own = conn is None
    if own:
        conn = connect_single(get_settings().progress_db_path)
    try:
        counts: dict[str, int] = {}
        # Children first when clearing, parents first when inserting, so the
        # intra-file foreign keys hold at every point.
        if mode == "replace":
            for table in reversed(PROGRESS_TABLES):
                conn.execute(f'DELETE FROM "{table}"')  # noqa: S608

        for table in PROGRESS_TABLES:
            rows = tables.get(table) or []
            counts[table] = 0
            for row in rows:
                cols = list(row.keys())
                collist = ", ".join(f'"{c}"' for c in cols)
                placeholders = ", ".join("?" * len(cols))
                conn.execute(
                    f'INSERT OR REPLACE INTO "{table}" ({collist}) VALUES ({placeholders})',  # noqa: S608
                    [row[c] for c in cols],
                )
                counts[table] += 1

        # Never leave the app without its singleton settings row.
        conn.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
        conn.commit()
        return counts
    finally:
        if own:
            conn.close()


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------
def snapshot_progress(label: str = "", stamp: str | None = None) -> Path:
    """Write a binary snapshot of progress.db using SQLite's online backup API.

    Not a file copy: copying a live SQLite database can capture a torn page or
    miss committed data still in the WAL. ``Connection.backup()`` takes a
    consistent snapshot while the app keeps running.
    """
    settings = get_settings()
    settings.ensure_dirs()
    stamp = stamp or _stamp()
    suffix = f"-{label}" if label else ""
    dest = settings.backup_dir / f"{SNAPSHOT_PREFIX}{stamp}{suffix}{SNAPSHOT_SUFFIX}"

    src = connect_single(settings.progress_db_path)
    try:
        out = sqlite3.connect(dest)
        try:
            src.backup(out)
        finally:
            out.close()
    finally:
        src.close()
    return dest


def snapshot_export(stamp: str | None = None) -> Path:
    """Write the gzipped JSON export alongside the binary snapshot."""
    settings = get_settings()
    settings.ensure_dirs()
    stamp = stamp or _stamp()
    dest = settings.backup_dir / f"{EXPORT_PREFIX}{stamp}{EXPORT_SUFFIX}"
    data = json.dumps(export_progress(), ensure_ascii=False, indent=1).encode("utf-8")
    with gzip.open(dest, "wb") as fh:
        fh.write(data)
    return dest


def run_backup(retention_days: int | None = None) -> dict:
    """The full nightly job: snapshot + export + prune. Safe to run any time."""
    settings = get_settings()
    retention = settings.backup_retention_days if retention_days is None else retention_days
    stamp = _stamp()

    snapshot = snapshot_progress(stamp=stamp)
    export = snapshot_export(stamp=stamp)
    pruned = prune(retention)

    log.info(
        "Backup complete: %s (%d bytes), %s (%d bytes), pruned %d old file(s)",
        snapshot.name,
        snapshot.stat().st_size,
        export.name,
        export.stat().st_size,
        len(pruned),
    )
    return {
        "snapshot": str(snapshot),
        "export": str(export),
        "pruned": [p.name for p in pruned],
        "retention_days": retention,
    }


def prune(retention_days: int | None = None) -> list[Path]:
    """Delete backups older than the retention window.

    Only touches files matching the backup naming pattern, and always keeps the
    most recent snapshot and export whatever their age — a long gap in use must
    never leave the backups directory empty.
    """
    settings = get_settings()
    retention = settings.backup_retention_days if retention_days is None else retention_days
    cutoff = datetime.now().timestamp() - retention * 86400

    removed: list[Path] = []
    for prefix, suffix in ((SNAPSHOT_PREFIX, SNAPSHOT_SUFFIX), (EXPORT_PREFIX, EXPORT_SUFFIX)):
        files = sorted(
            (p for p in settings.backup_dir.glob(f"{prefix}*{suffix}") if _stamp_of(p, prefix, suffix)),
            key=lambda p: p.name,
        )
        for path in files[:-1]:  # never the newest
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed.append(path)
    return removed


def last_backup_info() -> dict:
    """Summary for the admin API and the Me tab: is the cron actually running?"""
    settings = get_settings()
    settings.ensure_dirs()

    snapshots = sorted(
        p for p in settings.backup_dir.glob(f"{SNAPSHOT_PREFIX}*{SNAPSHOT_SUFFIX}")
        if _stamp_of(p, SNAPSHOT_PREFIX, SNAPSHOT_SUFFIX)
    )
    exports = sorted(
        p for p in settings.backup_dir.glob(f"{EXPORT_PREFIX}*{EXPORT_SUFFIX}")
        if _stamp_of(p, EXPORT_PREFIX, EXPORT_SUFFIX)
    )
    latest = snapshots[-1] if snapshots else None

    return {
        "backup_dir": str(settings.backup_dir),
        "snapshot_count": len(snapshots),
        "export_count": len(exports),
        "retention_days": settings.backup_retention_days,
        "scheduled_at": settings.backup_time,
        "last_backup_at": (
            datetime.fromtimestamp(latest.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
            if latest
            else None
        ),
        "last_backup_file": latest.name if latest else None,
        "last_backup_bytes": latest.stat().st_size if latest else None,
        "total_bytes": sum(p.stat().st_size for p in snapshots + exports),
    }
