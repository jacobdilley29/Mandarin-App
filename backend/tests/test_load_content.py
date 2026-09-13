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
