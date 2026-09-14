"""Loading generated content into the app (spec §3.1's draft gate).

The gate's whole point is that unfinished content never reaches Learn. That cuts
both ways: a draft with an out-of-scope sentence must not block the *finished*
units from loading either, which is what happened the first time a real
generation run left half-written drafts on disk — one bad draft sentence and
`make load-content` refused everything, including the units that had passed.
"""

from __future__ import annotations

import pytest

from app.validation import Violation
from scripts import load_content as lc


def _data(live_lessons: list[str], draft_lessons: list[str]) -> dict:
    return {"units": [
        {"id": "u_live", "status": "live",
         "lessons": [{"id": i} for i in live_lessons]},
        {"id": "u_draft", "status": "draft",
         "lessons": [{"id": i} for i in draft_lessons]},
    ]}


def _v(where: str) -> Violation:
    return Violation(where=f"{where} sentence 1", text="x", unknown=["嚇"])


def test_a_draft_violation_does_not_block_the_load():
    live, draft = lc.split_violations_by_status(
        _data(["l_live"], ["l_draft"]), [_v("l_draft")]
    )

    assert draft and not live, "a draft the learner cannot reach must not refuse the load"


def test_a_live_violation_still_blocks():
    """The gate has to keep working where it matters."""
    live, draft = lc.split_violations_by_status(
        _data(["l_live"], ["l_draft"]), [_v("l_live")]
    )

    assert live and not draft


def test_both_are_reported_separately():
    live, draft = lc.split_violations_by_status(
        _data(["l_live"], ["l_draft"]), [_v("l_live"), _v("l_draft")]
    )

    assert [v.where.split()[0] for v in live] == ["l_live"]
    assert [v.where.split()[0] for v in draft] == ["l_draft"]


def test_a_unit_with_no_explicit_status_counts_as_live():
    """status_of() defaults to live, and the split must agree with it."""
    data = {"units": [{"id": "u", "lessons": [{"id": "l"}]}]}

    live, draft = lc.split_violations_by_status(data, [_v("l")])

    assert live and not draft


# ---------------------------------------------------------------------------
# The loader does not take a unit's status on trust
# ---------------------------------------------------------------------------
def _unit(unit_id: str, *, generated: bool, status: str | None, finished: bool) -> dict:
    lesson = {
        "id": f"l_{unit_id}",
        "vocab": [{"traditional": "水", "pinyin": "shuǐ", "gloss": "water",
                   "example": {"hanzi": "我喝水"} if finished else {}}],
        "grammar": [{"id": "g1"}] if finished else [],
        "sentences": [{"tokens": ["水"]}] if finished else [],
        "dialogue": [{"hanzi": "水"}] if finished else [],
    }
    unit = {"id": unit_id, "title": "t", "lessons": [lesson]}
    if generated:
        unit["generated"] = True
    if status is not None:
        unit["status"] = status
    return unit


def test_a_generated_unit_marked_live_but_empty_is_caught():
    """The loader is the last stop before content reaches the learner.

    It used to take `status` on trust. That was wrong exactly once and it was
    enough: the themed skeleton builder omitted the field, the default is live,
    and 70 units with no grammar, sentences or dialogue were ready to teach.
    """
    data = {"units": [_unit("u_hsk2_01", generated=True, status="live", finished=False)]}

    found = lc.unfinished_live_units(data)

    assert [u for u, _ in found] == ["u_hsk2_01"]
    missing = dict(found)["u_hsk2_01"]
    assert "sentences_present" in missing and "grammar_seeded" in missing


def test_a_generated_unit_with_no_status_at_all_is_caught():
    """A forgotten status is not a missing status — it is the wrong one."""
    data = {"units": [_unit("u_hsk2_01", generated=True, status=None, finished=False)]}

    assert [u for u, _ in lc.unfinished_live_units(data)] == ["u_hsk2_01"]


def test_a_finished_generated_unit_loads_normally():
    data = {"units": [_unit("u_hsk2_01", generated=True, status="live", finished=True)]}

    assert lc.unfinished_live_units(data) == []


def test_a_generated_draft_is_not_flagged():
    """Drafts are unfinished by definition; the gate already keeps them out."""
    data = {"units": [_unit("u_hsk2_01", generated=True, status="draft", finished=False)]}

    assert lc.unfinished_live_units(data) == []


def test_hand_authored_units_are_left_alone():
    """status_of defaults to live for the curated units, which predate these
    checks. Applying the rule to them would refuse to load the curriculum."""
    data = {"units": [_unit("u_conv", generated=False, status=None, finished=False)]}

    assert lc.unfinished_live_units(data) == []
