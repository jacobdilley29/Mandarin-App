"""Restoring learner progress from a backup database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

SCHEMA = (Path(__file__).resolve().parents[1] / "app" / "schema.sql").read_text(encoding="utf-8")


def _db() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


@pytest.fixture
def backup() -> sqlite3.Connection:
    """A database as it was before content was rebuilt: extra vocab, progress."""
    c = _db()
    c.executemany(
        "INSERT INTO vocab (id, traditional, pinyin, gloss, hsk_level) VALUES (?,?,?,?,?)",
        [("v1", "水", "shuǐ", "water", 1), ("gone", "臟", "zāng", "dirty", 4)],
    )
    c.execute("INSERT INTO units (id,title,hsk_level,sort_order) VALUES ('u1','U',1,1)")
    c.execute("INSERT INTO lessons (id,unit_id,title,sort_order) VALUES ('l1','u1','L',1)")
    c.execute("INSERT INTO lessons (id,unit_id,title,sort_order) VALUES ('lgone','u1','X',2)")
    c.execute(
        "INSERT INTO lesson_progress (lesson_id,completed,best_score,unlocked) VALUES ('l1',1,0.9,1)"
    )
    c.execute(
        "INSERT INTO lesson_progress (lesson_id,completed,best_score,unlocked) VALUES ('lgone',1,1.0,1)"
    )
    for item in ("v1", "gone"):
        c.execute(
            """INSERT INTO srs_cards (item_type,item_id,card_type,state,stability,
                 difficulty,due,reps,lapses)
               VALUES ('vocab',?,'recognition','review',12.5,4.2,'2026-10-01T00:00:00',9,3)""",
            (item,),
        )
    c.execute("INSERT INTO review_log (card_id,rating,reviewed_at) VALUES (1,3,'2026-09-01T00:00:00')")
    c.execute("INSERT INTO daily_activity (day,minutes,reviews_done) VALUES ('2026-09-01',30.0,25)")
    c.execute("UPDATE settings SET anthropic_api_key='sk-key', phonetic='zhuyin', daily_new_limit=20")
    c.commit()
    return c


@pytest.fixture
def live() -> sqlite3.Connection:
    """A freshly rebuilt database: only the surviving content, no progress."""
    c = _db()
    c.execute("INSERT INTO vocab (id,traditional,pinyin,gloss,hsk_level) VALUES ('v1','水','shuǐ','water',1)")
    c.execute("INSERT INTO units (id,title,hsk_level,sort_order) VALUES ('u1','U',1,1)")
    c.execute("INSERT INTO lessons (id,unit_id,title,sort_order) VALUES ('l1','u1','L',1)")
    c.commit()
    return c


def _restore(backup, live, dry_run=False):
    from scripts.restore_progress import restore

    return restore(backup, live, dry_run)


def test_progress_for_surviving_content_is_restored(backup, live):
    report = _restore(backup, live)
    assert report["lesson_progress"]["restored"] == 1
    assert report["srs_cards"]["restored"] == 1
    row = live.execute("SELECT * FROM srs_cards").fetchone()
    assert (row["reps"], row["lapses"], row["state"]) == (9, 3, "review")
    assert row["stability"] == 12.5  # FSRS scheduling survives intact


def test_rows_pointing_at_deleted_content_are_dropped(backup, live):
    """A card for a word the rebuild removed would sit in the deck pointing at
    nothing, so it must not come back."""
    report = _restore(backup, live)
    assert report["srs_cards"]["dropped"] == 1
    assert report["lesson_progress"]["dropped"] == 1
    orphans = live.execute(
        """SELECT COUNT(*) n FROM srs_cards s LEFT JOIN vocab v ON v.id = s.item_id
           WHERE s.item_type = 'vocab' AND v.id IS NULL"""
    ).fetchone()["n"]
    assert orphans == 0


def test_review_log_follows_its_card_to_the_new_id(backup, live):
    _restore(backup, live)
    log = live.execute("SELECT card_id FROM review_log").fetchone()
    card = live.execute("SELECT id FROM srs_cards").fetchone()
    assert log is not None and log["card_id"] == card["id"]


def test_settings_and_api_key_come_back(backup, live):
    _restore(backup, live)
    row = live.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    assert row["anthropic_api_key"] == "sk-key"
    assert row["phonetic"] == "zhuyin"
    assert row["daily_new_limit"] == 20


def test_streak_history_comes_back(backup, live):
    _restore(backup, live)
    assert live.execute("SELECT COUNT(*) n FROM daily_activity").fetchone()["n"] == 1


def test_rerunning_does_not_duplicate(backup, live):
    _restore(backup, live)
    second = _restore(backup, live)
    assert second["srs_cards"]["restored"] == 0
    assert second["lesson_progress"]["restored"] == 0
    assert live.execute("SELECT COUNT(*) n FROM srs_cards").fetchone()["n"] == 1


def test_dry_run_writes_nothing(backup, live):
    report = _restore(backup, live, dry_run=True)
    assert report["srs_cards"]["restored"] == 1
    assert live.execute("SELECT COUNT(*) n FROM srs_cards").fetchone()["n"] == 0
