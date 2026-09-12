"""SQLite access — two files under data/, opened as one connection.

Spec §7 requires learner progress to live in its own database, separate from
application code and curriculum content, so that neither an app update nor a
content reseed can destroy it:

    data/content.db    curriculum + dictionary   — regenerable from content/*.json
    data/progress.db   SRS, completion, history  — irreplaceable, backed up

Both are opened on a single connection: content.db as ``main``, progress.db
ATTACHed as ``progress``. SQLite resolves an unqualified table name by searching
main and then each attached schema, so ordinary queries — including joins that
span the two files, e.g. srs_cards JOIN vocab — work exactly as they did when
this was one database. The two schema files keep their table names disjoint
(schema_meta vs progress_meta) so nothing is ever shadowed.

The one thing the split gives up is cross-file foreign keys, which SQLite cannot
enforce between attached databases. That is deliberate: a progress row must
outlive the content row it points at. See schema_progress.sql.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Iterator

from .config import get_settings

APP_DIR = Path(__file__).resolve().parent
CONTENT_SCHEMA_PATH = APP_DIR / "schema_content.sql"
PROGRESS_SCHEMA_PATH = APP_DIR / "schema_progress.sql"

CONTENT_SCHEMA_VERSION = "1"
PROGRESS_SCHEMA_VERSION = "1"

# Schema name the progress database is attached under. Queries rarely need it
# (unqualified names resolve fine), but backup/export code qualifies explicitly.
PROGRESS_SCHEMA = "progress"

# Which tables belong to which file. These lists are the single source of truth
# for the split: the legacy-DB migration routes by them, and the JSON exporter
# walks PROGRESS_TABLES. Keep them in step with the two schema_*.sql files —
# test_backup.py asserts they match the schemas exactly.
CONTENT_TABLES = (
    "dictionary",
    "vocab",
    "grammar",
    "units",
    "lessons",
    "lesson_vocab",
    "lesson_grammar",
    "exercises",
)

# Order matters: parents before children, so a restore satisfies foreign keys
# as it inserts (review_log -> srs_cards, talk_messages -> talk_sessions).
PROGRESS_TABLES = (
    "settings",
    "lesson_progress",
    "srs_cards",
    "review_log",
    "drill_errors",
    "tone_attempts",
    "band_state",
    "talk_sessions",
    "talk_messages",
    "daily_activity",
)

log = logging.getLogger(__name__)


def connect() -> sqlite3.Connection:
    """Open content.db with progress.db attached. The app's only connection type."""
    settings = get_settings()
    settings.ensure_dirs()
    conn = sqlite3.connect(settings.content_db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute(
        f"ATTACH DATABASE ? AS {PROGRESS_SCHEMA}", (str(settings.progress_db_path),)
    )
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute(f"PRAGMA {PROGRESS_SCHEMA}.journal_mode = WAL")
    return conn


def connect_single(path: Path) -> sqlite3.Connection:
    """Open one database file on its own, with no ATTACH.

    Schema bootstrap uses this so that unqualified CREATE TABLE lands in the
    intended file; backup/restore uses it to work on one file at a time.
    """
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db() -> None:
    """Create both databases from their schema files. Idempotent.

    Runs the one-time split of a pre-existing single-file DB first, so an
    instance upgrading from the old layout keeps all of its data.
    """
    settings = get_settings()
    settings.ensure_dirs()

    # Upgrade path from the pre-split layout (data/mandarin.db).
    from .migrate import split_legacy_db  # local import: avoids a cycle

    split_legacy_db()

    _init_one(
        settings.content_db_path,
        CONTENT_SCHEMA_PATH,
        "schema_meta",
        CONTENT_SCHEMA_VERSION,
    )
    _init_one(
        settings.progress_db_path,
        PROGRESS_SCHEMA_PATH,
        "progress_meta",
        PROGRESS_SCHEMA_VERSION,
    )

    conn = connect_single(settings.content_db_path)
    try:
        _migrate_content(conn)
        conn.commit()
    finally:
        conn.close()

    conn = connect_single(settings.progress_db_path)
    try:
        _migrate_progress(conn)
        conn.commit()
    finally:
        conn.close()


def _init_one(path: Path, schema_path: Path, meta_table: str, version: str) -> None:
    conn = connect_single(path)
    try:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        conn.execute(
            f"INSERT OR REPLACE INTO {meta_table} (key, value) VALUES ('version', ?)",
            (version,),
        )
        conn.commit()
    finally:
        conn.close()


def _migrate_content(conn: sqlite3.Connection) -> None:
    """Additive, idempotent migrations for content DBs predating a column.

    Existing units default to 'live' so an upgrade never hides content the
    learner already has; the next content load recomputes every status from the
    completeness checks anyway.
    """
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(units)").fetchall()}
    if "status" not in cols:
        conn.execute("ALTER TABLE units ADD COLUMN status TEXT NOT NULL DEFAULT 'live'")
    if "completeness" not in cols:
        conn.execute("ALTER TABLE units ADD COLUMN completeness TEXT")


def _migrate_progress(conn: sqlite3.Connection) -> None:
    """Additive, idempotent migrations for progress DBs created before a column existed.

    CREATE TABLE IF NOT EXISTS never alters an existing table, so new columns
    are added here by inspecting the live schema.
    """
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(settings)").fetchall()}
    if "anthropic_api_key" not in cols:
        conn.execute("ALTER TABLE settings ADD COLUMN anthropic_api_key TEXT")


def get_db() -> Iterator[sqlite3.Connection]:
    """FastAPI dependency: yields a connection, always closed afterwards."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()
