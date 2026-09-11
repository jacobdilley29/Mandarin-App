"""SQLite access — a single file under data/, initialised from schema.sql.

Kept deliberately small for Phase 0: a connection helper, schema bootstrap,
and a FastAPI dependency. Later phases build query modules on top of this.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator

from .config import get_settings

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
SCHEMA_VERSION = "0"  # Phase 0


def connect() -> sqlite3.Connection:
    settings = get_settings()
    settings.ensure_dirs()
    conn = sqlite3.connect(settings.db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db() -> None:
    """Create tables from schema.sql if they don't exist. Idempotent."""
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = connect()
    try:
        conn.executescript(schema_sql)
        _migrate(conn)
        conn.execute(
            "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('version', ?)",
            (SCHEMA_VERSION,),
        )
        conn.commit()
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Additive, idempotent migrations for DBs created before a column existed.

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
