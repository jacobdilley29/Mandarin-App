"""Graded reading on an FSRS schedule (spec §3.2, §3.6).

Three things are worth guarding, and they are the three that would be quietly
wrong if nobody checked:

  * a passage is only readable once its lesson is done — the prose is built from
    what that lesson taught, so serving it early is the out-of-scope reading the
    whole content pipeline exists to prevent;
  * rating a passage reschedules that passage and **nothing else** — the same
    rule practice sessions keep, and for the same reason;
  * and a passage card never shows up in the vocabulary review queue, which it
    cannot render and would only shrink.
"""

from __future__ import annotations

import json

import pytest

from app import practice, reading, review, srs

from .conftest import attached_conn

P1 = {
    "title": "去便利商店",
    "hanzi": "我要去便利商店買東西。便利商店有很多東西，也有咖啡。",
    "gloss": "I'm going to the convenience store to buy things. It has lots of things, and coffee too.",
}
P2 = {"title": "在銀行", "hanzi": "我去銀行。", "gloss": "I go to the bank."}
P3 = {"title": "草稿", "hanzi": "這是草稿。", "gloss": "This is a draft."}


@pytest.fixture
def conn(tmp_path):
    c = attached_conn(tmp_path, same_thread=False)
    c.executemany(
        "INSERT INTO units (id, title, hsk_level, sort_order, status) VALUES (?, ?, ?, ?, ?)",
        [
            ("u_shop", "便利商店", 1, 1, "live"),
            ("u_bank", "銀行郵局", 2, 2, "live"),
            ("u_draft", "未完成", 2, 3, "draft"),
        ],
    )
    c.executemany(
        """INSERT INTO lessons (id, unit_id, title, sort_order, passage)
           VALUES (?, ?, ?, ?, ?)""",
        [
            ("l_shop_1", "u_shop", "買東西", 1, json.dumps(P1, ensure_ascii=False)),
            ("l_shop_2", "u_shop", "結帳", 2, None),  # no passage yet
            ("l_bank_1", "u_bank", "開戶", 1, json.dumps(P2, ensure_ascii=False)),
            ("l_draft_1", "u_draft", "草稿", 1, json.dumps(P3, ensure_ascii=False)),
        ],
    )
    c.executemany(
        """INSERT INTO vocab (id, traditional, pinyin, gloss, zhuyin)
           VALUES (?, ?, ?, ?, ?)""",
        [
            ("v_bl", "便利商店", "biànlì shāngdiàn", "convenience store", "ㄅㄧㄢˋ"),
            ("v_mai", "買", "mǎi", "to buy", "ㄇㄞˇ"),
        ],
    )
    c.executemany(
        "INSERT INTO lesson_vocab (lesson_id, vocab_id, sort_order) VALUES (?, ?, ?)",
        [("l_shop_1", "v_bl", 0), ("l_shop_1", "v_mai", 1)],
    )
    c.commit()
    yield c
    c.close()


def complete(conn, lesson_id: str) -> None:
    conn.execute(
        """INSERT INTO lesson_progress (lesson_id, completed, best_score, unlocked)
           VALUES (?, 1, 1.0, 1)""",
        (lesson_id,),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# What the library offers
# ---------------------------------------------------------------------------
def test_only_live_units_contribute_passages(conn):
    """A draft unit's passage has not passed the scope check."""
    ids = [p["lesson_id"] for p in reading.library(conn)["passages"]]
    assert ids == ["l_shop_1", "l_bank_1"]
    assert "l_draft_1" not in ids


def test_a_lesson_without_a_passage_is_simply_absent(conn):
    assert "l_shop_2" not in [p["lesson_id"] for p in reading.library(conn)["passages"]]


def test_passages_come_in_curriculum_order(conn):
    ids = [p["lesson_id"] for p in reading.library(conn)["passages"]]
    assert ids == sorted(ids, key=["l_shop_1", "l_bank_1"].index)


def test_a_passage_is_locked_until_its_lesson_is_done(conn):
    lib = reading.library(conn)
    assert [p["unlocked"] for p in lib["passages"]] == [False, False]
    assert lib["unlocked"] == 0

    complete(conn, "l_shop_1")
    lib = reading.library(conn)
    assert lib["unlocked"] == 1
    assert lib["unread"] == 1
    assert next(p for p in lib["passages"] if p["lesson_id"] == "l_shop_1")["unlocked"]


def test_the_library_counts_what_is_waiting(conn):
    complete(conn, "l_shop_1")
    lib = reading.library(conn)
    assert lib["total"] == 2
    assert (lib["unlocked"], lib["unread"], lib["due"]) == (1, 1, 0)


def test_a_passage_carries_its_character_count(conn):
    p = next(p for p in reading.library(conn)["passages"] if p["lesson_id"] == "l_shop_1")
    assert p["chars"] == len(P1["hanzi"])


def test_malformed_passage_json_is_skipped_not_fatal(conn):
    conn.execute("UPDATE lessons SET passage = 'not json' WHERE id = 'l_bank_1'")
    conn.commit()
    assert [p["lesson_id"] for p in reading.library(conn)["passages"]] == ["l_shop_1"]


# ---------------------------------------------------------------------------
# Reading one
# ---------------------------------------------------------------------------
def test_a_passage_comes_with_the_words_its_lesson_taught(conn):
    complete(conn, "l_shop_1")
    p = reading.get_passage(conn, "l_shop_1")
    assert p["hanzi"] == P1["hanzi"]
    assert p["gloss"] == P1["gloss"]
    assert [v["traditional"] for v in p["vocab"]] == ["便利商店", "買"]
    assert p["vocab"][0]["zhuyin"] == "ㄅㄧㄢˋ"


def test_a_draft_units_passage_is_not_served(conn):
    complete(conn, "l_draft_1")
    assert reading.get_passage(conn, "l_draft_1") is None


def test_an_unknown_lesson_has_no_passage(conn):
    assert reading.get_passage(conn, "l_nope") is None


def test_reading_a_locked_passage_is_refused(conn):
    with pytest.raises(PermissionError):
        reading.record_read(conn, "l_bank_1", 3)


def test_reading_a_passage_that_does_not_exist_is_refused(conn):
    with pytest.raises(KeyError):
        reading.record_read(conn, "l_shop_2", 3)


def test_a_rating_has_to_be_one_of_the_four(conn):
    complete(conn, "l_shop_1")
    with pytest.raises(ValueError):
        reading.record_read(conn, "l_shop_1", 5)


# ---------------------------------------------------------------------------
# The schedule
# ---------------------------------------------------------------------------
def test_reading_a_passage_schedules_it(conn):
    complete(conn, "l_shop_1")
    out = reading.record_read(conn, "l_shop_1", 3)
    assert out["lesson_id"] == "l_shop_1"
    assert out["due"] is not None

    card = conn.execute(
        "SELECT * FROM srs_cards WHERE item_type='passage' AND item_id='l_shop_1'"
    ).fetchone()
    assert card["card_type"] == "reading"
    assert card["reps"] == 1


def test_again_brings_a_passage_back_sooner_than_easy(conn):
    complete(conn, "l_shop_1")
    complete(conn, "l_bank_1")
    hard = reading.record_read(conn, "l_shop_1", 1)
    easy = reading.record_read(conn, "l_bank_1", 4)
    assert hard["due"] < easy["due"], "a passage rated Again must resurface first"


def test_a_due_passage_shows_up_in_the_due_list(conn):
    complete(conn, "l_shop_1")
    reading.record_read(conn, "l_shop_1", 3)
    assert reading.due(conn) == []  # just read, not due again yet

    conn.execute(
        "UPDATE srs_cards SET due = '2020-01-01T00:00:00+00:00' WHERE item_type = 'passage'"
    )
    conn.commit()
    assert [p["lesson_id"] for p in reading.due(conn)] == ["l_shop_1"]
    assert reading.library(conn)["due"] == 1


# ---------------------------------------------------------------------------
# The rule that matters: reading must not disturb the vocabulary deck
# ---------------------------------------------------------------------------
def snapshot(conn) -> list[tuple]:
    return [
        tuple(r)
        for r in conn.execute(
            """SELECT id, item_type, item_id, state, stability, difficulty, due, reps, lapses
               FROM srs_cards WHERE item_type != 'passage' ORDER BY id"""
        )
    ]


def test_reading_a_passage_leaves_the_vocabulary_schedule_alone(conn):
    complete(conn, "l_shop_1")
    srs.ensure_new_card(conn, "vocab", "v_bl")
    srs.seed_mature(conn, "vocab", "v_mai")
    conn.commit()

    before = snapshot(conn)
    reading.record_read(conn, "l_shop_1", 1)  # the harshest rating there is
    assert snapshot(conn) == before


def test_a_passage_card_never_enters_the_review_queue(conn):
    """It cannot be rendered as a flashcard, and would shrink the queue."""
    complete(conn, "l_shop_1")
    reading.record_read(conn, "l_shop_1", 1)
    conn.execute("UPDATE srs_cards SET due = '2020-01-01T00:00:00+00:00'")
    conn.commit()

    assert srs.due_cards(conn, new_limit=20) == []
    assert review.build_queue(conn, new_limit=20) == []
    assert srs.counts(conn)["due"] == 0
    assert srs.counts(conn)["total"] == 0


def test_a_passage_never_takes_a_slot_in_a_needs_practice_set(conn):
    """The symptom isn't a passage appearing — it's a set coming back short.

    practice renders through the same code the review queue uses, so a passage
    card picked up here is dropped at render time. Nothing looks wrong; the set
    is just one item smaller than it says. So this asks for exactly two items
    with a passage ranked above both vocabulary cards.
    """
    complete(conn, "l_shop_1")
    reading.record_read(conn, "l_shop_1", 1)  # Again: one lapse
    conn.execute(
        "UPDATE srs_cards SET lapses = 9 WHERE item_type = 'passage'"
    )  # ranks first on lapses
    for vid in ("v_bl", "v_mai"):
        card = srs.ensure_new_card(conn, "vocab", vid)
        conn.execute("UPDATE srs_cards SET lapses = 3 WHERE id = ?", (card,))
    conn.commit()

    items = practice.weak_items(conn, limit=2)
    assert [i["item_id"] for i in items] == ["v_bl", "v_mai"]


def test_a_passage_never_takes_a_slot_in_a_known_material_set(conn):
    """Same shrinkage, on the other mode — which samples at random."""
    complete(conn, "l_shop_1")
    for vid in ("v_bl", "v_mai"):
        srs.seed_mature(conn, "vocab", vid)
    conn.execute("UPDATE srs_cards SET stability = 30")
    # Twenty mature passages against two words: sampling that pool unfiltered
    # returns a short set essentially every time.
    for i in range(20):
        srs.seed_mature(conn, "passage", f"l_fake_{i}", "reading")
    conn.execute("UPDATE srs_cards SET stability = 30")
    conn.commit()

    out = practice.known_material(conn, limit=2)
    assert sorted(i["item_id"] for i in out["items"]) == ["v_bl", "v_mai"]


# ---------------------------------------------------------------------------
# Over HTTP
# ---------------------------------------------------------------------------
@pytest.fixture
def client(conn):
    from fastapi.testclient import TestClient

    from app.db import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: conn
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_the_library_answers_over_http(client, conn):
    complete(conn, "l_shop_1")
    body = client.get("/api/reading").json()
    assert (body["total"], body["unlocked"], body["unread"]) == (2, 1, 1)


def test_due_is_a_route_not_a_lesson_id(client, conn):
    """/api/reading/due must not be read as /api/reading/{lesson_id}."""
    r = client.get("/api/reading/due")
    assert r.status_code == 200
    assert r.json() == {"passages": [], "count": 0}


def test_fetching_a_locked_passage_is_a_403(client, conn):
    assert client.get("/api/reading/l_bank_1").status_code == 403


def test_fetching_a_missing_passage_is_a_404(client, conn):
    assert client.get("/api/reading/l_nope").status_code == 404


def test_reading_and_rating_over_http(client, conn):
    complete(conn, "l_shop_1")
    got = client.get("/api/reading/l_shop_1").json()
    assert got["hanzi"] == P1["hanzi"]

    rated = client.post("/api/reading/answer", json={"lesson_id": "l_shop_1", "rating": 3})
    assert rated.status_code == 200
    assert rated.json()["lesson_id"] == "l_shop_1"

    refused = client.post("/api/reading/answer", json={"lesson_id": "l_bank_1", "rating": 3})
    assert refused.status_code == 403


def test_a_rating_outside_one_to_four_is_rejected(client, conn):
    complete(conn, "l_shop_1")
    r = client.post("/api/reading/answer", json={"lesson_id": "l_shop_1", "rating": 7})
    assert r.status_code == 422
