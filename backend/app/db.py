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
    def columns(table: str) -> set[str]:
        return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}

    settings_cols = columns("settings")
    if "anthropic_api_key" not in settings_cols:
        conn.execute("ALTER TABLE settings ADD COLUMN anthropic_api_key TEXT")
    if "phonetic" not in settings_cols:
        # Supersedes show_pinyin. Carry the old boolean over so an existing user
        # who had pinyin hidden does not get it switched back on.
        conn.execute(
            "ALTER TABLE settings ADD COLUMN phonetic TEXT NOT NULL DEFAULT 'pinyin'"
        )
        conn.execute(
            "UPDATE settings SET phonetic = CASE WHEN show_pinyin = 0 THEN 'off' ELSE 'pinyin' END"
        )

    vocab_cols = columns("vocab")
    if "example_zhuyin" not in vocab_cols:
        conn.execute("ALTER TABLE vocab ADD COLUMN example_zhuyin TEXT")
    if "tocfl_level" not in vocab_cols:
        conn.execute("ALTER TABLE vocab ADD COLUMN tocfl_level TEXT")

    unit_cols = columns("units")
    if "tocfl_level" not in unit_cols:
        conn.execute("ALTER TABLE units ADD COLUMN tocfl_level TEXT")
    if "tocfl_band" not in unit_cols:
        conn.execute("ALTER TABLE units ADD COLUMN tocfl_band TEXT")


def get_db() -> Iterator[sqlite3.Connection]:
    """FastAPI dependency: yields a connection, always closed afterwards."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()
