"""Grammar as a first-class module (spec §3.3, §3.6).

Grammar was taught in lessons and then never seen again: the review queue
dropped every non-vocab card on the floor, nothing recorded what a lesson built
on, and not one of the sixteen points carried a Taiwan-usage note. These cover
the three.
"""

from __future__ import annotations

import json

import pytest

from app import content, curriculum_source, exercises, review, srs
from app.validation import validate_grammar_prerequisites

from .conftest import attached_conn


GRAMMAR = {
    "id": "g_le", "title": "了 — a completed action",
    "pattern": "Subject + Verb + 了 + Object",
    "explanation": "了 marks that the action happened.",
    "examples": [{"hanzi": "我買了一個便當。", "pinyin": "p", "gloss": "I bought a boxed meal."}],
    "taiwan_note": "台灣口語常用「有 + 動詞」。",
}


def _lesson(lid="l1", grammar=(GRAMMAR,), requires=()):
    return {
        "id": lid, "title": "L", "sort_order": 1,
        "vocab": [{"id": "v1", "traditional": "買", "pinyin": "mǎi", "gloss": "to buy",
                   "example": {"hanzi": "我買了一個便當。"}}],
        "grammar": [dict(g) for g in grammar],
        "sentences": [{"tokens": ["我", "買", "了", "一個", "便當"], "gloss": "I bought a boxed meal.",
                       "pinyin": "p", "cloze_index": 1}],
        "dialogue": [{"hanzi": "你好"}],
        "requires_grammar": list(requires),
    }


@pytest.fixture
def conn(tmp_path):
    c = attached_conn(tmp_path)
    content.load_curriculum(c, {"meta": {}, "units": [
        {"id": "u1", "title": "U", "sort_order": 1, "hsk_level": 2, "lessons": [_lesson()]}
    ]})
    yield c
    c.close()


# ---------------------------------------------------------------------------
# Taiwan usage notes
# ---------------------------------------------------------------------------
def test_a_grammar_taiwan_note_survives_the_round_trip(conn):
    g = content.get_lesson_content(conn, "l1")["grammar"][0]
    assert g["taiwan_note"] == GRAMMAR["taiwan_note"]


def test_the_note_reaches_the_grammar_card(conn):
    lesson = content.get_lesson_content(conn, "l1")
    card = [e for e in exercises.build_stream(lesson, lesson["vocab"]) if e["kind"] == "grammar"][0]
    assert card["payload"]["taiwan_note"]


def test_the_shipped_curriculum_has_notes_where_taiwan_diverges():
    """Not one per point — most patterns are identical in both standards, and a
    manufactured note would devalue the real ones."""
    noted = [
        g for u in curriculum_source.load_live()["units"]
        for l in u["lessons"] for g in l.get("grammar", []) if g.get("taiwan_note")
    ]
    assert len(noted) >= 5
    for g in noted:
        assert len(g["taiwan_note"]) > 20


def test_the_big_taiwan_grammar_difference_is_documented():
    """有 + Verb for past actions is the most distinctive feature of Taiwan
    Mandarin grammar; if any note exists, that one should."""
    notes = " ".join(
        g.get("taiwan_note") or ""
        for u in curriculum_source.load_live()["units"]
        for l in u["lessons"] for g in l.get("grammar", [])
    )
    assert "有沒有" in notes and "有 + 動詞" in notes


# ---------------------------------------------------------------------------
# Prerequisites (spec §3.3)
# ---------------------------------------------------------------------------
def _curriculum(*lessons):
    return {"meta": {}, "units": [
        {"id": "u", "title": "U", "sort_order": 1, "hsk_level": 2, "lessons": list(lessons)}
    ]}


def test_a_lesson_may_require_grammar_taught_earlier():
    data = _curriculum(_lesson("l1"), _lesson("l2", grammar=(), requires=["g_le"]))
    assert validate_grammar_prerequisites(data).ok


def test_requiring_grammar_taught_later_is_refused():
    """The vocabulary side is enforced the same way — at load time, not by a lock."""
    data = _curriculum(_lesson("l1", grammar=(), requires=["g_le"]), _lesson("l2"))
    result = validate_grammar_prerequisites(data)

    assert not result.ok
    assert "not introduced yet" in result.violations[0].unknown[0]


def test_requiring_grammar_the_lesson_introduces_itself_is_refused():
    data = _curriculum(_lesson("l1", requires=["g_le"]))
    result = validate_grammar_prerequisites(data)

    assert not result.ok
    assert "same lesson" in result.violations[0].unknown[0]


def test_prerequisites_are_stored_and_returned(tmp_path):
    c = attached_conn(tmp_path)
    content.load_curriculum(c, _curriculum(_lesson("l1"), _lesson("l2", grammar=(), requires=["g_le"])))

    assert [g["id"] for g in content.get_lesson_content(c, "l2")["requires_grammar"]] == ["g_le"]
    assert content.get_lesson_content(c, "l1")["requires_grammar"] == []
    c.close()


def test_requires_is_distinct_from_introduces(tmp_path):
    """A lesson can lean on 了 without re-teaching it."""
    c = attached_conn(tmp_path)
    content.load_curriculum(c, _curriculum(_lesson("l1"), _lesson("l2", grammar=(), requires=["g_le"])))

    lesson = content.get_lesson_content(c, "l2")
    assert lesson["grammar"] == []
    assert len(lesson["requires_grammar"]) == 1
    c.close()


def test_prerequisites_do_not_gate_unlocking(tmp_path):
    """Unlock stays linear, so a gap in the graph can't strand the curriculum.

    l2 introduces its own point as well as requiring l1's, because a lesson with
    no grammar at all fails the Phase 2 completeness checks and its unit would
    be held back as a draft — which would prove nothing about unlocking.
    """
    c = attached_conn(tmp_path)
    other = dict(GRAMMAR, id="g_bi", title="比", pattern="A 比 B + Adjective")
    content.load_curriculum(
        c, _curriculum(_lesson("l1"), _lesson("l2", grammar=(other,), requires=["g_le"]))
    )

    lessons = content.get_curriculum(c)["units"][0]["lessons"]
    assert [l["id"] for l in lessons] == ["l1", "l2"]
    assert lessons[0]["unlocked"] is True
    # l2 requires grammar from l1 and is still reachable by the normal chain.
    assert lessons[1]["unlocked"] is False, "locked by lesson order, not by the graph"
    c.close()


def test_the_shipped_prerequisites_all_resolve():
    assert validate_grammar_prerequisites(curriculum_source.load()).ok


def test_the_shipped_curriculum_records_real_prerequisites():
    edges = sum(
        len(l.get("requires_grammar") or [])
        for u in curriculum_source.load_live()["units"] for l in u["lessons"]
    )
    assert edges >= 5, "the curated units genuinely build on earlier grammar"


# ---------------------------------------------------------------------------
# Grammar in the review queue (spec §3.6)
# ---------------------------------------------------------------------------
def test_grammar_cards_reach_the_review_queue(conn):
    """They used to be silently dropped — taught once, never reviewed."""
    srs.ensure_new_card(conn, "grammar", "g_le", "pattern")
    conn.commit()

    items = [i for i in review.build_queue(conn, 20) if i["item_type"] == "grammar"]
    assert len(items) == 1


@pytest.mark.parametrize("reps, kind", [(0, "pattern_recall"), (1, "particle_cloze"), (2, "pattern_build")])
def test_grammar_drills_rotate(conn, reps, kind):
    srs.ensure_new_card(conn, "grammar", "g_le", "pattern")
    conn.execute("UPDATE srs_cards SET reps = ? WHERE item_type='grammar'", (reps,))
    conn.commit()

    item = [i for i in review.build_queue(conn, 20) if i["item_type"] == "grammar"][0]
    assert item["kind"] == kind


def test_pattern_recall_offers_other_real_patterns(conn):
    srs.ensure_new_card(conn, "grammar", "g_le", "pattern")
    conn.commit()

    item = [i for i in review.build_queue(conn, 20) if i["item_type"] == "grammar"][0]
    assert item["answer"] == GRAMMAR["pattern"]
    assert sum(1 for o in item["options"] if o["correct"]) == 1


def test_particle_cloze_blanks_the_pattern_word(conn):
    srs.ensure_new_card(conn, "grammar", "g_le", "pattern")
    conn.execute("UPDATE srs_cards SET reps = 1 WHERE item_type='grammar'")
    conn.commit()

    item = [i for i in review.build_queue(conn, 20) if i["item_type"] == "grammar"][0]
    assert item["answer"] == "了"
    assert "＿" in item["masked"] and "了" not in item["masked"]


def test_pattern_build_tiles_reorder_to_the_model_sentence(conn):
    srs.ensure_new_card(conn, "grammar", "g_le", "pattern")
    conn.execute("UPDATE srs_cards SET reps = 2 WHERE item_type='grammar'")
    conn.commit()

    item = [i for i in review.build_queue(conn, 20) if i["item_type"] == "grammar"][0]
    assert sorted(item["tokens"]) == sorted(item["answer"])
    assert item["tokens"] != item["answer"], "the shuffle must actually move something"
    assert "了" in item["answer"], "the particle should be its own tile"


def test_a_grammar_point_with_no_examples_is_skipped_not_fatal(tmp_path):
    """A generated point that has no model sentences yet must not break review."""
    c = attached_conn(tmp_path)
    bare = dict(GRAMMAR, id="g_bare", examples=[])
    content.load_curriculum(c, _curriculum(_lesson("l1", grammar=(bare,))))
    srs.ensure_new_card(c, "grammar", "g_bare", "pattern")
    c.execute("UPDATE srs_cards SET reps = 1")
    c.commit()

    items = review.build_queue(c, 20)
    assert all(i["kind"] == "pattern_recall" for i in items if i["item_type"] == "grammar")
    c.close()


def test_vocab_cards_still_work_alongside_grammar(conn):
    srs.ensure_new_card(conn, "vocab", "v1", "recognition")
    srs.ensure_new_card(conn, "grammar", "g_le", "pattern")
    conn.commit()

    kinds = {i["item_type"] for i in review.build_queue(conn, 20)}
    assert kinds == {"vocab", "grammar"}


def test_completing_a_lesson_enrols_its_grammar(conn):
    content.record_result(conn, "l1", 1.0)

    row = conn.execute(
        "SELECT COUNT(*) FROM srs_cards WHERE item_type='grammar' AND item_id='g_le'"
    ).fetchone()[0]
    assert row == 1


def test_enrolling_grammar_twice_creates_one_card(conn):
    content.record_result(conn, "l1", 1.0)
    content.record_result(conn, "l1", 1.0)

    assert conn.execute("SELECT COUNT(*) FROM srs_cards WHERE item_type='grammar'").fetchone()[0] == 1


# ---------------------------------------------------------------------------
# Particle cloze as a lesson drill (spec §3.3)
# ---------------------------------------------------------------------------
def test_lessons_include_a_particle_cloze(conn):
    lesson = content.get_lesson_content(conn, "l1")
    stream = exercises.build_stream(lesson, lesson["vocab"])
    items = [e for e in stream if e["kind"] == "particle_cloze"]

    assert len(items) == 1
    p = items[0]["payload"]
    assert p["answer"] == "了" and "＿" in p["masked"]
    assert p["grammar_id"] == "g_le"


def test_particle_cloze_is_graded():
    assert "particle_cloze" in exercises.GRADABLE_KINDS


def test_the_vocab_cloze_and_particle_cloze_ask_different_things(conn):
    """Same sentence, different question: one tests the word, one the pattern."""
    lesson = content.get_lesson_content(conn, "l1")
    stream = exercises.build_stream(lesson, lesson["vocab"])

    vocab_cloze = [e for e in stream if e["kind"] == "cloze"][0]["payload"]
    particle_cloze = [e for e in stream if e["kind"] == "particle_cloze"][0]["payload"]
    assert vocab_cloze["options"] != particle_cloze["options"]
    assert particle_cloze["answer"] == "了"


def test_multi_character_particles_win_over_their_prefixes():
    """Otherwise 有沒有 gets blanked as 有, and the drill becomes nonsense."""
    import random

    g = {"id": "g_y", "title": "有沒有", "pattern": "Subject + 有沒有 + Noun？"}
    sentences = [{"tokens": ["你", "有沒有", "空"], "gloss": "Are you free?"}]
    item = exercises._particle_cloze(g, sentences, random.Random(0))

    assert item["answer"] == "有沒有"
    assert item["masked"] == "你＿空"


def test_a_point_whose_particle_is_absent_yields_no_drill():
    import random

    g = {"id": "g_z", "title": "把", "pattern": "Subject + 把 + Object + Verb"}
    assert exercises._particle_cloze(g, [{"tokens": ["我", "很", "好"]}], random.Random(0)) is None


def test_the_two_particle_lists_agree():
    """review.py and exercises.py each need the list; they must not drift."""
    assert set(exercises.PARTICLES) == set(review.PARTICLES)
