"""Shared pytest fixtures.

The app runs against two SQLite files — content.db as ``main`` with progress.db
ATTACHed as ``progress`` (see app/db.py). Tests mirror that exactly rather than
using a single flat schema, so anything that would break under the split
(shadowed table names, a query that silently reads the wrong file) fails here
instead of in production.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[1] / "app"
CONTENT_SCHEMA = (APP_DIR / "schema_content.sql").read_text(encoding="utf-8")
PROGRESS_SCHEMA = (APP_DIR / "schema_progress.sql").read_text(encoding="utf-8")


def attached_conn(tmp_path: Path) -> sqlite3.Connection:
    """A content+progress connection over two real files under tmp_path.

    Real files rather than :memory: — an in-memory ATTACH would give each
    schema its own private database and hide exactly the cross-file behaviour
    these tests exist to check.
    """
    content_path = tmp_path / "content.db"
    progress_path = tmp_path / "progress.db"

    # Build each file on its own connection so unqualified CREATE TABLE lands
    # in the right one, just as app.db.init_db does.
    for path, schema in ((content_path, CONTENT_SCHEMA), (progress_path, PROGRESS_SCHEMA)):
        c = sqlite3.connect(path)
        c.executescript(schema)
        c.commit()
        c.close()

    conn = sqlite3.connect(content_path)
    conn.row_factory = sqlite3.Row
    conn.execute("ATTACH DATABASE ? AS progress", (str(progress_path),))
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@pytest.fixture
def conn(tmp_path):
    c = attached_conn(tmp_path)
    # A couple of vocab items to attach cards to.
    c.executemany(
        "INSERT INTO vocab (id, traditional, pinyin, gloss, hsk_level) VALUES (?, ?, ?, ?, ?)",
        [
            ("v1", "水", "shuǐ", "water", 1),
            ("v2", "便當", "biàndāng", "boxed meal", 2),
            ("v3", "茶", "chá", "tea", 1),
        ],
    )
    c.commit()
    yield c
    c.close()
