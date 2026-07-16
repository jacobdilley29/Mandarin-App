"""Tests for progress tracking (spec §3.6)."""

from __future__ import annotations

from datetime import date, timedelta

from app import progress, srs


def test_record_activity_accumulates(conn):
    progress.record_activity(conn, reviews=2, lessons=1, minutes=5)
    progress.record_activity(conn, reviews=3, minutes=1)
    row = conn.execute("SELECT * FROM daily_activity WHERE day = ?", (date.today().isoformat(),)).fetchone()
    assert row["reviews_done"] == 5
    assert row["lessons_done"] == 1
    assert abs(row["minutes"] - 6.0) < 1e-6


def test_streak_counts_consecutive_days(conn):
    for i in range(3):  # today, yesterday, day before
        d = (date.today() - timedelta(days=i)).isoformat()
        progress.record_activity(conn, reviews=1, day=d)
    # a gap two days before breaks it
    progress.record_activity(conn, reviews=1, day=(date.today() - timedelta(days=5)).isoformat())
    p = progress.get_progress(conn)
    assert p["streak"] == 3


def test_tone_attempt_feeds_accuracy(conn):
    progress.record_tone_attempt(conn, "水", 1, 1)
    progress.record_tone_attempt(conn, "便當", 1, 2)
    p = progress.get_progress(conn)
    assert p["tone_accuracy"] == round(2 / 3, 3)
    assert len(p["tone_trend"]) == 2


def test_words_by_hsk_bands_by_stability(conn):
    # A mature card and a new card at different levels.
    srs.seed_mature(conn, "vocab", "v1", "recognition")  # v1 hsk1
    # bump stability high so it lands in the mature band
    conn.execute("UPDATE srs_cards SET stability = 30 WHERE item_id = 'v1'")
    srs.ensure_new_card(conn, "vocab", "v2", "recognition")  # v2 hsk2, new
    conn.commit()
    p = progress.get_progress(conn)
    by_lvl = {w["hsk_level"]: w for w in p["words_by_hsk"]}
    assert by_lvl[1]["mature"] == 1
    assert by_lvl[2]["learning"] == 1
    assert p["total_known"] == 2
    assert p["total_mature"] == 1


def test_retention_from_review_log(conn):
    cid = srs.ensure_new_card(conn, "vocab", "v1", "recognition")
    srs.apply_review(conn, cid, 3)  # Good
    cid2 = srs.ensure_new_card(conn, "vocab", "v2", "recognition")
    srs.apply_review(conn, cid2, 1)  # Again
    p = progress.get_progress(conn)
    assert p["retention"] == 0.5


def test_weakest_grammar_from_drill_errors(conn):
    conn.execute("INSERT INTO grammar (id, title, pattern, explanation, examples) VALUES ('g1','了','P','E','[]')")
    for _ in range(3):
        conn.execute("INSERT INTO drill_errors (grammar_id, detail) VALUES ('g1','cloze')")
    conn.commit()
    p = progress.get_progress(conn)
    assert p["weakest_grammar"][0]["id"] == "g1"
    assert p["weakest_grammar"][0]["errors"] == 3
