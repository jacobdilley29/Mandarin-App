"""Is the live curriculum continuous? (spec §3.1)

completeness.py asks whether a unit has its parts. This asks whether the learner
can actually read it: walking only the live units, in order, was every character
taught before it appears?

The case that prompted this: six generated units were promoted above thirteen
still-empty drafts holding 232 words. Every one of those units passed the draft
gate and the content validator, because both judge a unit against the *whole*
curriculum — drafts included — rather than against the sequence the learner
walks. Nothing reported it, and it took a hand-written script to find.
"""

from __future__ import annotations

import pytest

from app import curriculum_source, sequence


# Fixture words must NOT be in the placement pool (老師 學生 朋友 … 茶 飯 菜 …),
# which is known from lesson one and so can never be a hole. 水, 湯 and 餐廳 are
# outside it; 茶 is inside, and using it here quietly made a test unfalsifiable.
def _unit(uid: str, order: int, teaches: list[str], sentences: list[list[str]],
          status: str = "live") -> dict:
    return {
        "id": uid,
        "sort_order": order,
        "status": status,
        "lessons": [{
            "id": f"l_{uid}",
            "sort_order": 1,
            "vocab": [{"id": f"v_{w}", "traditional": w} for w in teaches],
            "sentences": [{"tokens": t} for t in sentences],
        }],
    }


def _curriculum(*units: dict) -> dict:
    return {"meta": {"function_words": []}, "units": list(units)}


# ---------------------------------------------------------------------------
# The two ways to make a hole
# ---------------------------------------------------------------------------
def test_a_word_taught_earlier_in_the_live_sequence_is_fine():
    data = _curriculum(
        _unit("u1", 1, ["水"], [["水"]]),
        _unit("u2", 2, ["餐廳"], [["水", "餐廳"]]),
    )

    assert sequence.holes(data) == []


def test_a_live_unit_leaning_on_a_draft_is_a_hole():
    """The 232-word case: the word exists, but only where the learner never goes."""
    data = _curriculum(
        _unit("u_draft", 1, ["水"], [["水"]], status="draft"),
        _unit("u_live", 2, ["餐廳"], [["水", "餐廳"]]),
    )

    found = sequence.holes(data)

    assert [h.char for h in found] == ["水"]
    assert found[0].taught_in == "u_draft"
    assert "still a draft" in found[0].reason


def test_a_word_taught_later_is_a_hole():
    """Forward reach — 較 used in an HSK 2 unit but taught in an HSK 3 one."""
    data = _curriculum(
        _unit("u1", 1, ["水"], [["水", "湯"]]),
        _unit("u2", 2, ["湯"], [["湯"]]),
    )

    found = sequence.holes(data)

    assert [h.char for h in found] == ["湯"]
    assert found[0].taught_in == "u2"
    assert "comes later" in found[0].reason


def test_a_word_taught_nowhere_says_so():
    """嚇 appeared in generated content and is in no unit at all."""
    data = _curriculum(_unit("u1", 1, ["水"], [["水", "嚇"]]))

    found = sequence.holes(data)

    assert found[0].char == "嚇"
    assert found[0].taught_in is None
    assert found[0].reason == "taught nowhere in the curriculum"


def test_the_placement_pool_is_never_a_hole():
    """老師 is seeded as mastered before lesson one; it is not missing."""
    data = _curriculum(_unit("u1", 1, ["水"], [["老師", "水"]]))

    assert sequence.holes(data) == []


# ---------------------------------------------------------------------------
# Shape of the report
# ---------------------------------------------------------------------------
def test_live_only_drops_drafts_and_keeps_the_rest():
    data = _curriculum(
        _unit("u1", 1, ["水"], [["水"]]),
        _unit("u2", 2, ["湯"], [["湯"]], status="draft"),
    )

    assert [u["id"] for u in sequence.live_only(data)["units"]] == ["u1"]


def test_a_unit_with_no_explicit_status_counts_as_live():
    """status_of defaults to live for the hand-authored units; agree with it."""
    data = {"meta": {"function_words": []}, "units": [
        {"id": "u", "sort_order": 1, "lessons": [{
            "id": "l", "sort_order": 1,
            "vocab": [{"id": "v", "traditional": "水"}],
            "sentences": [{"tokens": ["水"]}],
        }]},
    ]}

    assert [u["id"] for u in sequence.live_only(data)["units"]] == ["u"]
    assert sequence.holes(data) == []


def test_the_summary_names_the_drafts_being_waited_on():
    """"Which drafts do I need to fill?" is the question worth answering."""
    data = _curriculum(
        _unit("u_draft", 1, ["水"], [["水"]], status="draft"),
        _unit("u_live", 2, ["餐廳"], [["水", "餐廳"]]),
    )

    summary = sequence.summary(data)

    assert summary["holes"] == 1
    assert summary["lessons_affected"] == 1
    assert summary["waiting_on_drafts"] == ["u_draft"]
    assert summary["characters"] == ["水"]


# ---------------------------------------------------------------------------
# The committed content
# ---------------------------------------------------------------------------
def test_the_shipped_curriculum_has_no_holes():
    """Starts honest, so any regression shows up as a failure rather than a shrug."""
    summary = sequence.summary(curriculum_source.load())

    assert summary["holes"] == 0, (
        f"live lessons reach for untaught characters: {summary['characters']}; "
        f"waiting on drafts {summary['waiting_on_drafts']}"
    )


def test_the_check_can_actually_fail(monkeypatch):
    """A check that cannot fail is decoration. Demote a unit, expect complaints."""
    data = curriculum_source.load()
    for unit in data["units"]:
        if unit["id"] == "u_food":
            unit["status"] = curriculum_source.STATUS_DRAFT

    summary = sequence.summary(data)

    assert summary["holes"] > 0
    assert summary["waiting_on_drafts"] == ["u_food"]
