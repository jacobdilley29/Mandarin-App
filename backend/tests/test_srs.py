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
    assert out["seeded_mature"] == 1
    assert out["seeded_new"] == 1
    # v1 is the only HSK 1 item asked and it was right, so that level is cleared;
    # v2 (HSK 2) was missed, so HSK 2 is not.
    assert out["levels_cleared"] == [1]
    done = conn.execute("SELECT placement_done FROM settings WHERE id = 1").fetchone()["placement_done"]
    assert done == 1


def test_placement_completes_lessons_of_cleared_levels(conn):
    """Clearing a level must unlock past it — placement used to only seed cards,
    leaving the learner behind a strictly linear unlock chain."""
    conn.execute(
        "INSERT INTO units (id, title, hsk_level, sort_order) VALUES ('u1', 'U', 1, 1)"
    )
    conn.executemany(
        "INSERT INTO lessons (id, unit_id, title, sort_order) VALUES (?, 'u1', ?, ?)",
        [("l1", "L1", 1), ("l2", "L2", 2)],
    )
    conn.commit()

    out = review.seed_placement(conn, [
        {"vocab_id": "v1", "correct": True, "hsk_level": 1},
        {"vocab_id": "v3", "correct": True, "hsk_level": 1},
    ])
    assert out["levels_cleared"] == [1]
    completed = {
        r["lesson_id"] for r in conn.execute(
            "SELECT lesson_id FROM lesson_progress WHERE completed = 1"
        ).fetchall()
    }
    assert completed == {"l1", "l2"}


def test_placement_stops_clearing_at_the_first_shaky_level(conn):
    """Levels clear from the bottom up. Clearing a higher level while a lower one
    is shaky would strand the learner behind a lesson they cannot reach."""
    out = review.seed_placement(conn, [
        {"vocab_id": "v1", "correct": False, "hsk_level": 1},
        {"vocab_id": "v2", "correct": True, "hsk_level": 2},
    ])
    assert out["levels_cleared"] == []


def test_grammar_cards_are_rendered_in_the_queue(conn):
    """Grammar was enrolled but never shown — build_queue dropped every card
    whose item_type was not 'vocab'."""
    import json as _json

    conn.execute(
        """INSERT INTO grammar (id, title, pattern, explanation, examples, sort_order)
           VALUES ('g1', '有沒有', 'Subject + 有沒有 + Noun？', 'Ask whether it exists.', ?, 0)""",
        (_json.dumps([{"hanzi": "他有沒有便當？", "pinyin": "Tā yǒu méiyǒu biàndāng?",
                       "gloss": "Does he have a boxed meal?"}], ensure_ascii=False),),
    )
    conn.execute(
        """INSERT INTO grammar (id, title, pattern, explanation, examples, sort_order)
           VALUES ('g2', '比', 'A 比 B + Adjective', 'Comparison.', '[]', 1)"""
    )
    conn.commit()
    srs.ensure_new_card(conn, "grammar", "g1", "grammar")

    items = review.build_queue(conn, new_limit=10)
    cards = [i for i in items if i["kind"] == "grammar"]
    assert cards, "grammar card was not rendered"
    card = cards[0]
    assert card["prompt_hanzi"] == "他有沒有便當？"
    assert card["answer"] == "Subject + 有沒有 + Noun？"
    assert sum(1 for o in card["options"] if o["correct"]) == 1
    assert card["explanation"]


def test_grammar_card_without_examples_is_skipped(conn):
    """A point with no example sentence has nothing to prompt with; it must be
    dropped rather than rendered blank."""
    conn.execute(
        """INSERT INTO grammar (id, title, pattern, explanation, examples, sort_order)
           VALUES ('g3', 'x', 'P', 'e', '[]', 0)"""
    )
    conn.commit()
    srs.ensure_new_card(conn, "grammar", "g3", "grammar")
    assert not [i for i in review.build_queue(conn, new_limit=10) if i["kind"] == "grammar"]
