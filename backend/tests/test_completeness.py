"""Per-unit completeness and the draft gate (spec §3.1).

These exist because of commit 08e90b7, which grew the curriculum from 149 to
1,208 words mechanically — no sentences, no dialogues, raw dictionary glosses —
and placed the result ahead of the hand-authored Taiwan units, making it the
first thing in Learn. It was reverted.

Every test below is a way that can happen again. The gate has to hold without
anyone remembering to check it.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from app import completeness, content, curriculum_source

from .conftest import attached_conn


def unit(uid="u_x", *, title="Unit", sort_order=0, status=None, lessons=None, **kw):
    u = {"id": uid, "title": title, "sort_order": sort_order,
         "lessons": lessons if lessons is not None else [lesson()]}
    if status:
        u["status"] = status
    u.update(kw)
    return u


def lesson(lid="l_x", *, vocab=True, grammar=True, sentences=True, dialogue=True,
           example=True, gloss=True):
    return {
        "id": lid,
        "title": "Lesson",
        "sort_order": 0,
        "vocab": [{
            "id": "v1", "traditional": "水",
            "pinyin": "shuǐ" if gloss else None,
            "gloss": "water" if gloss else None,
            "taiwan_note": "note",
            "example": {"hanzi": "我要水。"} if example else {},
        }] if vocab else [],
        "grammar": [{"id": "g1", "title": "g", "pattern": "p", "explanation": "e",
                     "examples": []}] if grammar else [],
        "sentences": [{"tokens": ["我", "要", "水"]}] if sentences else [],
        "dialogue": [{"hanzi": "你好"}] if dialogue else [],
    }


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------
def test_a_fully_populated_unit_is_complete():
    report = completeness.evaluate_unit(unit())
    assert report.complete and report.missing == []
    assert report.status == curriculum_source.STATUS_LIVE


@pytest.mark.parametrize(
    "kwargs, missing_check",
    [
        ({"vocab": False}, "vocab_seeded"),
        ({"grammar": False}, "grammar_seeded"),
        ({"sentences": False}, "sentences_present"),
        ({"example": False}, "examples_present"),
        ({"gloss": False}, "vocab_glossed"),
    ],
)
def test_each_missing_piece_blocks_the_unit(kwargs, missing_check):
    report = completeness.evaluate_unit(unit(lessons=[lesson(**kwargs)]))
    assert missing_check in report.missing
    assert report.status == curriculum_source.STATUS_DRAFT


def test_the_shape_that_got_reverted_is_a_draft():
    """Vocabulary with glosses but no sentences, dialogue or grammar.

    This is exactly what 08e90b7 shipped into Learn.
    """
    mechanical = unit(lessons=[lesson(grammar=False, sentences=False, dialogue=False)])
    report = completeness.evaluate_unit(mechanical)

    assert not report.complete
    assert {"grammar_seeded", "sentences_present"} <= set(report.missing)
    assert report.status == curriculum_source.STATUS_DRAFT


def test_missing_dialogue_alone_does_not_block():
    """Optional checks are reported, not enforced."""
    report = completeness.evaluate_unit(unit(lessons=[lesson(dialogue=False)]))
    assert report.complete
    assert "dialogue_present" in report.missing_optional


def test_an_empty_unit_is_never_complete():
    """`all()` over no lessons is vacuously true — that must not mean 'done'."""
    report = completeness.evaluate_unit(unit(lessons=[]))
    assert not report.complete
    assert "has_lessons" in report.missing


def test_a_unit_whose_lessons_are_all_empty_is_never_complete():
    report = completeness.evaluate_unit(unit(lessons=[{"id": "l", "title": "t"}]))
    assert not report.complete


def test_counts_are_reported_for_the_coverage_view():
    report = completeness.evaluate_unit(unit())
    assert report.counts["lessons"] == 1
    assert report.counts["vocab"] == 1
    assert report.counts["examples"] == 1


# ---------------------------------------------------------------------------
# Status resolution — declaring a unit live cannot override the checks
# ---------------------------------------------------------------------------
def test_declaring_an_incomplete_unit_live_does_not_make_it_live():
    """The gate must not be only as good as whoever last edited the file."""
    mislabelled = unit(status="live", lessons=[lesson(sentences=False)])
    assert completeness.resolved_status(mislabelled) == curriculum_source.STATUS_DRAFT


def test_a_draft_stays_draft_even_when_complete():
    """Explicitly holding a finished unit back is allowed."""
    held = unit(status="draft")
    assert completeness.evaluate_unit(held).complete
    assert completeness.resolved_status(held) == curriculum_source.STATUS_DRAFT


def test_units_without_a_status_default_to_live():
    """Hand-authored units predate the field and must keep being taught."""
    u = unit()
    assert "status" not in u
    assert completeness.resolved_status(u) == curriculum_source.STATUS_LIVE


# ---------------------------------------------------------------------------
# The gate, end to end through the database
# ---------------------------------------------------------------------------
@pytest.fixture
def loaded(tmp_path):
    """A DB holding one finished unit and one mechanical draft — the draft first."""
    conn = attached_conn(tmp_path)
    data = {
        "meta": {},
        "units": [
            # sort_order 0: ahead of the good unit, exactly as the revert described.
            unit("u_generated", title="Generated", sort_order=0,
                 lessons=[lesson("l_gen", grammar=False, sentences=False, dialogue=False)]),
            unit("u_curated", title="便利商店", sort_order=1, lessons=[lesson("l_cur")]),
        ],
    }
    content.load_curriculum(conn, data)
    yield conn
    conn.close()


def test_a_draft_unit_never_reaches_the_learn_map(loaded):
    curriculum = content.get_curriculum(loaded)
    ids = [u["id"] for u in curriculum["units"]]

    assert ids == ["u_curated"], "an incomplete unit reached the learner"


def test_a_draft_cannot_displace_the_curated_unit_as_lesson_one(loaded):
    """The reverted bug in one assertion: sort_order must not beat the gate."""
    curriculum = content.get_curriculum(loaded)
    first_unit = curriculum["units"][0]

    assert first_unit["title"] == "便利商店"
    assert first_unit["lessons"][0]["unlocked"] is True


def test_draft_lessons_do_not_gate_the_unlock_chain(loaded):
    """A draft mid-sequence must not lock everything behind an invisible lesson."""
    curriculum = content.get_curriculum(loaded)
    lessons = [l for u in curriculum["units"] for l in u["lessons"]]

    assert lessons and lessons[0]["unlocked"] is True


def test_status_and_checklist_are_persisted(loaded):
    rows = {r["id"]: r for r in loaded.execute("SELECT id, status, completeness FROM units")}

    assert rows["u_generated"]["status"] == "draft"
    assert rows["u_curated"]["status"] == "live"
    assert "sentences_present" in json.loads(rows["u_generated"]["completeness"])["missing"]


def test_draft_content_is_still_loaded_into_the_database(loaded):
    """Staged, not discarded — generation needs the rows to work on."""
    assert loaded.execute(
        "SELECT COUNT(*) FROM lessons WHERE unit_id = 'u_generated'"
    ).fetchone()[0] == 1


def test_completing_a_draft_promotes_it(tmp_path):
    """The promotion path: fill in what's missing, reload, and it goes live."""
    conn = attached_conn(tmp_path)
    incomplete = unit("u_p", lessons=[lesson("l_p", sentences=False)])
    content.load_curriculum(conn, {"meta": {}, "units": [incomplete]})
    assert content.get_curriculum(conn)["units"] == []

    content.load_curriculum(conn, {"meta": {}, "units": [unit("u_p", lessons=[lesson("l_p")])]})
    assert [u["id"] for u in content.get_curriculum(conn)["units"]] == ["u_p"]
    conn.close()


def test_a_unit_that_regresses_is_demoted_again(tmp_path):
    """Status is recomputed on every load, never trusted from a previous one."""
    conn = attached_conn(tmp_path)
    content.load_curriculum(conn, {"meta": {}, "units": [unit("u_r")]})
    assert [u["id"] for u in content.get_curriculum(conn)["units"]] == ["u_r"]

    content.load_curriculum(
        conn, {"meta": {}, "units": [unit("u_r", lessons=[lesson("l_x", sentences=False)])]}
    )
    assert content.get_curriculum(conn)["units"] == []
    conn.close()


# ---------------------------------------------------------------------------
# The committed curriculum
# ---------------------------------------------------------------------------
def test_every_live_unit_in_the_shipped_curriculum_really_is_complete():
    """Drafts are expected — a live unit that fails its own checks is not."""
    data = curriculum_source.load()
    by_id = {u["id"]: u for u in data["units"]}

    for report in completeness.evaluate(data):
        if completeness.resolved_status(by_id[report.unit_id]) == curriculum_source.STATUS_LIVE:
            assert report.complete, f"{report.unit_id} is live but missing {report.missing}"


def test_the_hand_authored_units_are_the_live_ones():
    s = completeness.summary(curriculum_source.load())
    assert s["live"] == 14, "the curated Taiwan curriculum should be what's taught"
    assert s["draft"] > 0, "the HSK skeleton should be staged, not absent"


def test_coverage_summary_names_what_each_draft_is_missing():
    s = completeness.summary({"meta": {}, "units": [unit("u_d", lessons=[lesson(sentences=False)])]})
    assert s["draft"] == 1
    assert s["report"][0]["missing"] == ["sentences_present"]
    assert all(k in completeness.DESCRIPTIONS for k in s["report"][0]["missing"])
