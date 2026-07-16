"""Shared pytest fixtures — an isolated in-memory DB seeded from schema.sql."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

SCHEMA = (Path(__file__).resolve().parents[1] / "app" / "schema.sql").read_text(encoding="utf-8")


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
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
