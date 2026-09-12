"""Adaptive placement check (spec §3.1).

The old placement asked 30 recognition questions over HSK 1–2 and could not
place a learner above HSK 2 — which measures nothing for someone at TOCFL A2/B1.
These tests pin the two things that fixes: the walk reaches the right band, and
a short sample is never mistaken for knowledge of a whole level.
"""

from __future__ import annotations

import pytest

from app import content, levels, placement

from .conftest import attached_conn


@pytest.fixture
def conn(tmp_path):
    """Content spanning all four bands, plus a live unit with drill sentences."""
    c = attached_conn(tmp_path)
    for level in levels.BANDS:
        c.executemany(
            "INSERT INTO vocab (id, traditional, pinyin, gloss, hsk_level, example_hanzi)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            [
                (f"v{level}_{i}", f"詞{level}{i}", "cí", f"word {level}-{i}; second sense", level,
                 f"我要詞{level}{i}。")
                for i in range(20)
            ],
        )
    c.execute("INSERT INTO units (id, title, hsk_level, status) VALUES ('u2', 'U', 2, 'live')")
    c.execute(
        """INSERT INTO lessons (id, unit_id, title, sentences) VALUES
           ('l2', 'u2', 'L', '[{"tokens": ["我", "要", "水"], "gloss": "I want water",
             "pinyin": "wo yao shui"}]')"""
    )
    c.commit()
    yield c
    c.close()


def _play(conn, knows_up_to: int) -> dict:
    """Walk the whole quiz as a learner who knows every band up to `knows_up_to`."""
    band, visited, seen = placement.START_BAND, set(), set()
    while band is not None:
        r = placement.build_round(conn, band, seen)
        results = []
        for it in r["items"]:
            if it.get("vocab_id"):
                seen.add(it["vocab_id"])
            results.append({"vocab_id": it.get("vocab_id"), "correct": band <= knows_up_to})
        out = placement.record_round(conn, band, results)
        visited.add(band)
        band = placement.next_band(band, out["status"], visited)
    return placement.finalize(conn)


# ---------------------------------------------------------------------------
# The walk lands in the right place
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "knows_up_to, expected_start_hsk",
    [(0, 1), (1, 2), (2, 3), (3, 4), (4, 4)],
)
def test_the_walk_finds_the_right_starting_band(conn, knows_up_to, expected_start_hsk):
    summary = _play(conn, knows_up_to)
    assert summary["start_at"]["hsk_level"] == expected_start_hsk


def test_an_a2_b1_learner_is_not_capped_at_hsk2(conn):
    """The specific failure of the old quiz, as an assertion."""
    summary = _play(conn, 3)

    assert summary["start_at"]["hsk_level"] == 4
    assert summary["start_at"]["cefr"] == "B1"
    assert summary["start_at"]["label"] == "Level 3"


def test_the_walk_is_short(conn):
    """Three or four rounds, not an exhaustive test of 1,250 words."""
    band, visited, rounds = placement.START_BAND, set(), 0
    while band is not None and rounds < 20:
        rounds += 1
        out = placement.record_round(
            conn, band, [{"vocab_id": None, "correct": True}] * placement.ROUND_SIZE
        )
        visited.add(band)
        band = placement.next_band(band, out["status"], visited)

    assert rounds <= len(levels.BANDS)


def test_the_walk_cannot_loop_between_two_bands(conn):
    """A fluctuating score must terminate, not ping-pong forever."""
    assert placement.next_band(2, placement.STATUS_KNOWN, {2, 3}) is None
    assert placement.next_band(2, placement.STATUS_TO_LEARN, {1, 2}) is None


def test_the_walk_stops_at_the_edges(conn):
    assert placement.next_band(4, placement.STATUS_KNOWN, {4}) is None
    assert placement.next_band(1, placement.STATUS_TO_LEARN, {1}) is None


def test_a_partial_band_is_the_boundary_and_ends_the_quiz(conn):
    assert placement.next_band(2, placement.STATUS_PARTIAL, {2}) is None

    placement.record_round(conn, 3, [
        *[{"vocab_id": f"v3_{i}", "correct": True} for i in range(5)],
        *[{"vocab_id": f"v3_{i}", "correct": False} for i in range(5, 8)],
    ])
    assert placement.estimated_level(conn)["hsk_level"] == 3


@pytest.mark.parametrize(
    "score, status",
    [(1.0, "known"), (0.8, "known"), (0.75, "partial"), (0.5, "partial"), (0.49, "to_learn"), (0.0, "to_learn")],
)
def test_score_thresholds(score, status):
    assert placement.classify(score) == status


# ---------------------------------------------------------------------------
# Item kinds — the spec names three
# ---------------------------------------------------------------------------
def test_a_round_mixes_recognition_listening_and_sentence_building(conn):
    kinds = {i["kind"] for i in placement.build_round(conn, 2)["items"]}
    assert kinds == {"recognition", "listening", "sentence_build"}


def test_listening_items_hide_the_characters(conn):
    """Otherwise it's a reading test with a speaker icon."""
    for item in placement.build_round(conn, 2)["items"]:
        if item["kind"] == "listening":
            assert item["audio_text"]
            assert "char" not in item and "pinyin" not in item


def test_sentence_items_are_actually_shuffled(conn):
    for item in placement.build_round(conn, 2)["items"]:
        if item["kind"] == "sentence_build":
            assert item["tokens"] != item["answer"]
            assert sorted(item["tokens"]) == sorted(item["answer"])


def test_a_band_with_no_live_sentences_still_builds_a_full_round(conn):
    """Band 4 has vocab but no live unit — it must degrade, not break."""
    r = placement.build_round(conn, 4)
    assert len(r["items"]) == placement.ROUND_SIZE
    assert {i["kind"] for i in r["items"]} == {"recognition", "listening"}


def test_rounds_do_not_repeat_words_already_asked(conn):
    first = placement.build_round(conn, 2)
    seen = {i["vocab_id"] for i in first["items"] if i["vocab_id"]}

    second = placement.build_round(conn, 2, seen)
    assert not seen & {i["vocab_id"] for i in second["items"] if i["vocab_id"]}


def test_options_are_trimmed_dictionary_glosses(conn):
    """Raw CC-CEDICT entries are unreadable as buttons and give the answer away
    by being four times longer than every distractor."""
    for item in placement.build_round(conn, 2)["items"]:
        for o in item.get("options") or []:
            assert len(o["text"]) <= 50, o["text"]


def test_every_choice_item_has_exactly_one_right_answer(conn):
    for item in placement.build_round(conn, 3)["items"]:
        if item.get("options"):
            assert sum(1 for o in item["options"] if o["correct"]) == 1


# ---------------------------------------------------------------------------
# What gets seeded — the part that could poison the review queue
# ---------------------------------------------------------------------------
def test_only_tested_words_get_cards(conn):
    """A band judged 'known' must NOT seed mature cards for all 600 of its words.

    Claiming that on the strength of eight questions would fill the review queue
    with material Jacob has never seen, and FSRS would take months to work the
    error back out.
    """
    placement.record_round(conn, 4, [{"vocab_id": "v4_0", "correct": True}] * 1)

    cards = conn.execute("SELECT COUNT(*) FROM srs_cards").fetchone()[0]
    band4_words = conn.execute("SELECT COUNT(*) FROM vocab WHERE hsk_level = 4").fetchone()[0]
    assert cards == 1
    assert band4_words > 1, "the fixture should have more band-4 words than were tested"


def test_correct_answers_seed_mature_and_misses_seed_new(conn):
    out = placement.record_round(conn, 2, [
        {"vocab_id": "v2_0", "correct": True},
        {"vocab_id": "v2_1", "correct": False},
    ])
    assert (out["seeded_known"], out["seeded_new"]) == (1, 1)

    states = {r["item_id"]: r["state"] for r in conn.execute("SELECT item_id, state FROM srs_cards")}
    assert states == {"v2_0": "review", "v2_1": "new"}


def test_sentence_items_score_without_seeding_a_card(conn):
    """They have no single vocab_id — they still count toward the band score."""
    out = placement.record_round(conn, 2, [
        {"vocab_id": None, "correct": True},
        {"vocab_id": None, "correct": False},
    ])
    assert out["total"] == 2 and out["correct"] == 1
    assert conn.execute("SELECT COUNT(*) FROM srs_cards").fetchone()[0] == 0


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def test_band_verdicts_are_stored(conn):
    placement.record_round(conn, 3, [{"vocab_id": "v3_0", "correct": True}])

    row = conn.execute("SELECT * FROM band_state WHERE hsk_level = 3").fetchone()
    assert row["status"] == "known" and row["score"] == 1.0 and row["sampled"] == 1


def test_replaying_a_band_replaces_its_verdict(conn):
    placement.record_round(conn, 3, [{"vocab_id": "v3_0", "correct": True}])
    placement.record_round(conn, 3, [{"vocab_id": "v3_1", "correct": False}])

    rows = conn.execute("SELECT status FROM band_state WHERE hsk_level = 3").fetchall()
    assert len(rows) == 1 and rows[0]["status"] == "to_learn"


def test_untested_bands_report_as_not_assessed(conn):
    placement.record_round(conn, 2, [{"vocab_id": "v2_0", "correct": True}])

    states = {b["hsk_level"]: b for b in placement.band_states(conn)}
    assert states[2]["assessed"] is True
    assert states[4]["assessed"] is False and states[4]["status"] is None


def test_every_band_carries_its_tocfl_label(conn):
    for b in placement.band_states(conn):
        assert b["label"] and b["sublabel"].startswith("HSK")
        assert b["label"] != b["sublabel"], "TOCFL leads, HSK is the secondary line"


def test_finalize_marks_placement_done(conn):
    placement.record_round(conn, 2, [{"vocab_id": "v2_0", "correct": True}])
    placement.finalize(conn)

    assert conn.execute("SELECT placement_done FROM settings WHERE id=1").fetchone()[0] == 1


def test_reset_clears_the_verdict_but_keeps_review_history(conn):
    """Redoing a placement estimate must not cost real SRS progress."""
    placement.record_round(conn, 2, [{"vocab_id": "v2_0", "correct": True}])
    placement.finalize(conn)

    placement.reset(conn)

    assert conn.execute("SELECT COUNT(*) FROM band_state").fetchone()[0] == 0
    assert conn.execute("SELECT placement_done FROM settings WHERE id=1").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM srs_cards").fetchone()[0] == 1


def test_summary_reports_deck_counts(conn):
    _play(conn, 2)
    summary = placement.summary(conn)

    assert summary["known_cards"] > 0
    assert summary["caveat"], "the TOCFL/HSK word-count caveat should reach the UI"


# ---------------------------------------------------------------------------
# The verdict has to open the content it names
# ---------------------------------------------------------------------------
@pytest.fixture
def curriculum(conn):
    """Live units across HSK 2, 3 and 4 — one lesson each, in level order."""
    for level, uid in ((2, "u_a"), (3, "u_b"), (4, "u_c")):
        conn.execute(
            "INSERT OR REPLACE INTO units (id, title, hsk_level, status, sort_order)"
            " VALUES (?, ?, ?, 'live', ?)",
            (uid, f"Unit {level}", level, level),
        )
        conn.execute(
            "INSERT INTO lessons (id, unit_id, title, sort_order) VALUES (?, ?, ?, 1)",
            (f"l_{uid}", uid, f"Lesson {level}"),
        )
    conn.commit()
    return conn


def _open_lessons(conn) -> set[str]:
    return {
        l["id"]
        for u in content.get_curriculum(conn)["units"]
        for l in u["lessons"]
        if l["unlocked"]
    }


def test_without_placement_the_chain_is_the_only_way_in(curriculum):
    """Spec §3.1's rule, unchanged for anyone who skips the check."""
    assert len(_open_lessons(curriculum)) == 1


def test_placement_opens_the_level_it_names(curriculum):
    """The bug: it said "Starting you at Level 3" and opened nothing.

    Being told you belong at HSK 4 and then handed lesson one of the beginner
    unit, with everything else locked, is the check failing to do its job.
    """
    _play(curriculum, knows_up_to=4)
    assert placement.estimated_level(curriculum)["hsk_level"] == 4

    assert _open_lessons(curriculum) == {"l2", "l_u_a", "l_u_b", "l_u_c"}


def test_it_opens_no_further_than_the_level_it_names(curriculum):
    """A learner placed mid-curriculum must not be handed the whole thing."""
    _play(curriculum, knows_up_to=2)
    placed = placement.estimated_level(curriculum)["hsk_level"]
    assert placed == 3

    opened = _open_lessons(curriculum)
    assert "l_u_b" in opened, "the level he was placed at is open"
    assert "l_u_c" not in opened, f"HSK 4 is above the placement at HSK {placed}"


def test_opened_is_not_the_same_as_completed(curriculum):
    """Otherwise placement would inflate the progress dashboard for free."""
    _play(curriculum, knows_up_to=4)

    lessons = [l for u in content.get_curriculum(curriculum)["units"] for l in u["lessons"]]
    assert all(l["unlocked"] for l in lessons)
    assert not any(l["completed"] for l in lessons)


def test_the_api_gate_agrees_with_what_the_screen_shows(curriculum):
    """A lesson shown as open must actually open — one unlock rule, not two."""
    _play(curriculum, knows_up_to=4)

    for u in content.get_curriculum(curriculum)["units"]:
        for l in u["lessons"]:
            assert content.is_unlocked(curriculum, l["id"]) == l["unlocked"], l["id"]
