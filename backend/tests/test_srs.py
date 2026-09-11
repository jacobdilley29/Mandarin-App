"""Tests for FSRS scheduling (spec §7 testing expectations)."""

from __future__ import annotations

from datetime import datetime, timezone

from app import review, srs


def _new_card(conn, item_id="v1") -> int:
    return srs.ensure_new_card(conn, "vocab", item_id, "recognition")


def _due(conn, card_id: int) -> datetime:
    row = conn.execute("SELECT due FROM srs_cards WHERE id = ?", (card_id,)).fetchone()
    return datetime.fromisoformat(row["due"])


def test_ensure_new_card_is_idempotent(conn):
    a = srs.ensure_new_card(conn, "vocab", "v1", "recognition")
    b = srs.ensure_new_card(conn, "vocab", "v1", "recognition")
    assert a == b
    n = conn.execute("SELECT COUNT(*) AS n FROM srs_cards").fetchone()["n"]
    assert n == 1


def test_higher_rating_schedules_further_out(conn):
    # Four identical fresh cards, one per rating; better ratings → later due.
    dues = {}
    for rating in (1, 2, 3, 4):
        cid = srs.ensure_new_card(conn, "vocab", "v1", f"c{rating}")
        srs.apply_review(conn, cid, rating)
        dues[rating] = _due(conn, cid)
    assert dues[1] <= dues[2] <= dues[3] <= dues[4]
    # Easy should be strictly later than Again.
    assert dues[4] > dues[1]


def test_review_increments_reps_and_logs(conn):
    cid = _new_card(conn)
    srs.apply_review(conn, cid, 3)
    row = conn.execute("SELECT reps, state FROM srs_cards WHERE id = ?", (cid,)).fetchone()
    assert row["reps"] == 1
    assert row["state"] in ("learning", "review")
    logs = conn.execute("SELECT COUNT(*) AS n FROM review_log WHERE card_id = ?", (cid,)).fetchone()["n"]
    assert logs == 1


def test_again_counts_a_lapse_on_a_review_card(conn):
    cid = srs.seed_mature(conn, "vocab", "v1", "recognition")
    before = conn.execute("SELECT lapses FROM srs_cards WHERE id = ?", (cid,)).fetchone()["lapses"]
    srs.apply_review(conn, cid, 1)  # Again
    after = conn.execute("SELECT lapses FROM srs_cards WHERE id = ?", (cid,)).fetchone()["lapses"]
    assert after == before + 1


def test_seed_mature_is_review_state_due_in_future(conn):
    cid = srs.seed_mature(conn, "vocab", "v2", "recognition")
    row = conn.execute("SELECT state, stability, due FROM srs_cards WHERE id = ?", (cid,)).fetchone()
    assert row["state"] == "review"
    assert row["stability"] > 0
    assert datetime.fromisoformat(row["due"]) > datetime.now(timezone.utc)


def test_mature_card_not_in_todays_queue_but_new_is(conn):
    srs.seed_mature(conn, "vocab", "v1", "recognition")  # due in ~10 days
    srs.ensure_new_card(conn, "vocab", "v2", "recognition")  # due now
    cards = srs.due_cards(conn, new_limit=15)
    item_ids = {c["item_id"] for c in cards}
    assert "v2" in item_ids  # new card surfaces
    assert "v1" not in item_ids  # mature card deferred


def test_apply_review_rejects_bad_rating(conn):
    cid = _new_card(conn)
    try:
        srs.apply_review(conn, cid, 9)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_build_queue_renders_items(conn):
    srs.ensure_new_card(conn, "vocab", "v1", "recognition")
    srs.ensure_new_card(conn, "vocab", "v3", "recognition")
    items = review.build_queue(conn, new_limit=15)
    assert len(items) == 2
    for it in items:
        assert "card_id" in it and "options" in it and "kind" in it
        assert sum(1 for o in it["options"] if o["correct"]) == 1


def test_placement_seeds_mature_and_new(conn):
    out = review.seed_placement(
        conn,
        [
            {"vocab_id": "v1", "correct": True},
            {"vocab_id": "v2", "correct": False},
        ],
    )
    assert out == {"seeded_mature": 1, "seeded_new": 1}
    done = conn.execute("SELECT placement_done FROM settings WHERE id = 1").fetchone()["placement_done"]
    assert done == 1
