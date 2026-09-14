"""Extra practice sessions (spec §3.6 "needs practice", §3.1 "review known material").

The load-bearing test here is test_a_practice_session_leaves_the_schedule_alone:
practice that quietly moved due dates, or charged a lapse for a fumbled extra
rep, would punish the learner for practising. Everything else checks that the
two modes select the right material.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import practice, progress, srs

from .conftest import attached_conn

FUTURE = (datetime.now(timezone.utc) + timedelta(days=40)).isoformat()


def _card(conn, item_id, *, item_type="vocab", state="review", stability=30.0, lapses=0, reps=5):
    cid = srs.ensure_new_card(conn, item_type, item_id)
    conn.execute(
        """UPDATE srs_cards
              SET state = ?, stability = ?, difficulty = 5.0, lapses = ?, reps = ?, due = ?
            WHERE id = ?""",
        (state, stability, lapses, reps, FUTURE, cid),
    )
    conn.commit()
    return cid


@pytest.fixture
def conn(tmp_path):
    c = attached_conn(tmp_path)
    c.executemany(
        """INSERT INTO vocab (id, traditional, pinyin, gloss, hsk_level, example_hanzi, example_gloss)
           VALUES (?,?,?,?,?,?,?)""",
        [
            ("v_shui", "水", "shuǐ", "water", 1, "我要喝水", "I want to drink water"),
            ("v_biandang", "便當", "biàndāng", "boxed meal", 2, "買一個便當", "buy a boxed meal"),
            ("v_cha", "茶", "chá", "tea", 1, "喝茶", "drink tea"),
            ("v_jiu", "就", "jiù", "then", 2, "我就走", "I'll go then"),
            ("v_cai", "才", "cái", "only then", 3, "他才來", "he only just came"),
        ],
    )
    c.execute(
        """INSERT INTO grammar (id, title, pattern, explanation, examples)
           VALUES ('g_le', '了 — a completed action', 'V + 了', 'marks completion',
                   '[{"hanzi": "我吃飽了", "pinyin": "wǒ chī bǎo le", "gloss": "I am full"}]')"""
    )
    c.commit()
    yield c
    c.close()


# ---------------------------------------------------------------------------
# Needs practice (§3.6)
# ---------------------------------------------------------------------------
def test_a_lapsed_item_outranks_a_healthy_one(conn):
    """§3.6's "repeated SRS lapses" — the signal the whole view exists for."""
    _card(conn, "v_shui", lapses=0)
    lapsed = _card(conn, "v_biandang", lapses=4)

    items = practice.weak_items(conn)
    assert items[0]["card_id"] == lapsed
    assert "forgotten 4x" in items[0]["why"]


def test_a_healthy_card_is_not_offered_as_a_weak_spot(conn):
    _card(conn, "v_shui", lapses=0)

    assert practice.weak_items(conn) == []


def test_drill_errors_count_as_trouble(conn):
    """Wrong answers inside lessons are evidence too, not just SRS lapses."""
    clean = _card(conn, "v_shui")
    erring = _card(conn, "v_cha")
    for _ in range(3):
        conn.execute("INSERT INTO drill_errors (vocab_id) VALUES ('v_cha')")
    conn.commit()

    items = practice.weak_items(conn)
    assert [i["card_id"] for i in items] == [erring]
    assert clean not in [i["card_id"] for i in items]
    assert "3 drill errors" in items[0]["why"]


def test_poor_tone_attempts_count_as_trouble(conn):
    """§3.6 names "poor pronunciation-attempt history" explicitly."""
    cid = _card(conn, "v_cha")
    conn.execute(
        "INSERT INTO tone_attempts (target_text, correct, total) VALUES ('茶', 1, 4)"
    )
    conn.commit()

    items = practice.weak_items(conn)
    assert [i["card_id"] for i in items] == [cid]
    assert "tones 25%" in items[0]["why"]


def test_good_tone_attempts_do_not_make_an_item_weak(conn):
    _card(conn, "v_cha")
    conn.execute(
        "INSERT INTO tone_attempts (target_text, correct, total) VALUES ('茶', 9, 10)"
    )
    conn.commit()

    assert practice.weak_items(conn) == []


def test_signals_stack_so_the_worst_item_comes_first(conn):
    """Bad in two ways should outrank bad in one — that's the whole ranking."""
    one_signal = _card(conn, "v_shui", lapses=2)
    both = _card(conn, "v_biandang", lapses=2)
    for _ in range(3):
        conn.execute("INSERT INTO drill_errors (vocab_id) VALUES ('v_biandang')")
    conn.commit()

    assert [i["card_id"] for i in practice.weak_items(conn)] == [both, one_signal]


def test_grammar_trouble_surfaces_too(conn):
    """Phase 4 put grammar in the review queue; practice has to follow."""
    cid = _card(conn, "g_le", item_type="grammar", lapses=3)
    conn.execute("INSERT INTO drill_errors (grammar_id) VALUES ('g_le')")
    conn.commit()

    items = practice.weak_items(conn)
    assert items[0]["card_id"] == cid
    assert items[0]["item_type"] == "grammar"
    assert items[0]["kind"] in ("pattern_recall", "particle_cloze", "pattern_build")


def test_weak_items_are_playable_drills(conn):
    """Rendered by the review renderers, so the drill UI needs nothing new."""
    _card(conn, "v_shui", lapses=2)

    item = practice.weak_items(conn)[0]
    assert item["kind"]
    assert len(item["options"]) >= 2
    assert sum(1 for o in item["options"] if o["correct"]) == 1


def test_the_limit_is_respected(conn):
    for vid in ("v_shui", "v_biandang", "v_cha", "v_jiu", "v_cai"):
        _card(conn, vid, lapses=2)

    assert len(practice.weak_items(conn, limit=3)) == 3


def test_nothing_weak_yet_explains_itself(conn):
    """An empty screen has to say why, not just sit there blank."""
    _card(conn, "v_shui")

    result = practice.needs_practice(conn)
    assert result["items"] == []
    assert result["empty_reason"]


# ---------------------------------------------------------------------------
# Known material (§3.1)
# ---------------------------------------------------------------------------
def test_known_material_pulls_mastered_items(conn):
    mature = _card(conn, "v_shui", stability=practice.MATURE_STABILITY + 5)

    result = practice.known_material(conn)
    assert [i["card_id"] for i in result["items"]] == [mature]


def test_known_material_excludes_new_cards(conn):
    """§3.1 says "already-mastered" — an unseen word is the opposite of that."""
    srs.ensure_new_card(conn, "vocab", "v_cha")
    conn.commit()

    assert practice.known_material(conn)["items"] == []


def test_known_material_excludes_shaky_cards(conn):
    """In review but not yet holding: still being learned, not mastered."""
    _card(conn, "v_shui", stability=practice.MATURE_STABILITY - 1)

    assert practice.known_material(conn)["items"] == []


def test_nothing_mastered_yet_explains_itself(conn):
    result = practice.known_material(conn)
    assert result["items"] == []
    assert result["empty_reason"]


# ---------------------------------------------------------------------------
# The rule that matters
# ---------------------------------------------------------------------------
def _snapshot(conn) -> list[tuple]:
    return [tuple(r) for r in conn.execute("SELECT * FROM srs_cards ORDER BY id")]


def test_a_practice_session_leaves_the_schedule_alone(conn):
    """The regression guard for the whole feature.

    Drilling a word you keep forgetting must not move its due date, change its
    stability, or add a lapse — practice is free, or it isn't practice.
    """
    _card(conn, "v_shui", lapses=3)
    _card(conn, "v_biandang", stability=40.0)
    _card(conn, "g_le", item_type="grammar", lapses=2)
    before = _snapshot(conn)

    for _ in range(3):
        practice.needs_practice(conn)
        practice.known_material(conn)
        practice.record_session(conn, answered=12, correct=4)

    assert _snapshot(conn) == before


def test_practice_never_writes_a_review_log(conn):
    """A review_log row is what a real review leaves behind; practice isn't one."""
    _card(conn, "v_shui", lapses=3)

    practice.needs_practice(conn)
    practice.record_session(conn, answered=10, correct=10)

    assert conn.execute("SELECT COUNT(*) AS n FROM review_log").fetchone()["n"] == 0


def test_practice_still_counts_toward_the_streak(conn):
    """Free of scheduling consequences, but not invisible — it's study time."""
    practice.record_session(conn, answered=10, correct=8)

    row = conn.execute("SELECT minutes, reviews_done FROM daily_activity").fetchone()
    assert row["minutes"] == pytest.approx(progress.review_minutes(10))
    assert row["reviews_done"] == 0, "practice reps are not scheduled reviews"


def test_record_session_reports_what_it_did(conn):
    assert practice.record_session(conn, answered=9, correct=7) == {
        "answered": 9,
        "correct": 7,
        "srs_unchanged": True,
    }
