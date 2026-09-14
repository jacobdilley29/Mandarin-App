"""Teaching order (spec §3.1).

Every hand-authored unit used to be taught before every generated one. The
authored units are HSK 2-4, so a learner met 銀行郵局 before any HSK 1 material.
That was a deliberate reaction to a real failure — generated units were once
unthemed word bags with no sentences, and level-ordering put them at the front of
Learn — but they are themed, complete and gated now, and the reason has expired.

What makes this delicate is that character scope is *cumulative in sort_order*.
Moving a unit earlier removes everything that used to precede it from what its
sentences may use, so a reorder can invalidate content that was correct — and
paid for — when it was generated. Hence a tool that measures before it writes.
"""

from __future__ import annotations

import json

import pytest

from app import curriculum_source as cs
from scripts import reorder_units as ru


def _unit(unit_id, level, order, *, generated, sentences=None):
    return {
        "id": unit_id, "title": unit_id, "hsk_level": level, "sort_order": order,
        "generated": generated,
        "lessons": [{
            "id": f"l_{unit_id}", "title": "L", "sort_order": 1,
            "vocab": [{"id": f"v_{unit_id}", "traditional": "水", "pinyin": "shuǐ",
                       "gloss": "water"}],
            "grammar": [], "dialogue": [],
            "sentences": sentences if sentences is not None else [],
        }],
    }


# ---------------------------------------------------------------------------
# The order itself
# ---------------------------------------------------------------------------
def test_beginner_material_comes_before_advanced():
    """The whole point: HSK 1 before the authored HSK 3 and 4 units."""
    units = [
        _unit("u_bank", 4, 12, generated=False),
        _unit("u_dir", 3, 4, generated=False),
        _unit("u_conv", 2, 1, generated=False),
        _unit("u_hsk1_01", 1, 15, generated=True),
    ]

    assert [u["id"] for u in ru.level_order(units)] == [
        "u_hsk1_01", "u_conv", "u_dir", "u_bank",
    ]


def test_authored_units_still_lead_their_own_level():
    """便利商店 opens HSK 2 — it just no longer opens the whole course."""
    units = [
        _unit("u_hsk2_01", 2, 21, generated=True),
        _unit("u_conv", 2, 1, generated=False),
        _unit("u_food", 2, 2, generated=False),
    ]

    assert [u["id"] for u in ru.level_order(units)] == [
        "u_conv", "u_food", "u_hsk2_01",
    ]


def test_existing_order_is_kept_within_a_group():
    units = [
        _unit("b", 2, 2, generated=False),
        _unit("a", 2, 1, generated=False),
        _unit("c", 2, 3, generated=False),
    ]

    assert [u["id"] for u in ru.level_order(units)] == ["a", "b", "c"]


def test_sort_order_is_renumbered_from_one():
    units = [_unit("u_hsk1_01", 1, 15, generated=True), _unit("u_conv", 2, 1, generated=False)]

    assert [u["sort_order"] for u in ru.renumbered(units)] == [1, 2]


# ---------------------------------------------------------------------------
# It must never touch a lesson
# ---------------------------------------------------------------------------
@pytest.fixture
def source(tmp_path, monkeypatch):
    monkeypatch.setattr(cs, "CONTENT_DIR", tmp_path)
    monkeypatch.setattr(cs, "MANIFEST_PATH", tmp_path / "curriculum.json")
    monkeypatch.setattr(cs, "UNITS_DIR", tmp_path / "units")
    cs.split({"meta": {"function_words": []}, "units": [
        _unit("u_bank", 4, 1, generated=False,
              sentences=[{"tokens": ["水"], "pinyin": "p", "gloss": "g"}]),
        _unit("u_hsk1_01", 1, 2, generated=True,
              sentences=[{"tokens": ["水"], "pinyin": "p", "gloss": "g"}]),
    ]})
    return tmp_path


def test_applying_rewrites_order_and_nothing_else(source, capsys):
    """Lesson content is the expensive artifact in this project.

    Reordering must never be a reason to lose it — which rules out reaching for
    build_skeleton, whose rebuild would discard every generated lesson.
    """
    before = json.loads((cs.UNITS_DIR / "u_hsk1_01.json").read_text(encoding="utf-8"))

    ru.main(["--apply"])

    after = json.loads((cs.UNITS_DIR / "u_hsk1_01.json").read_text(encoding="utf-8"))
    assert after["sort_order"] == 1, "HSK 1 now leads"
    assert after["lessons"] == before["lessons"], "not one lesson changed"
    assert json.loads((cs.UNITS_DIR / "u_bank.json").read_text(encoding="utf-8"))["sort_order"] == 2


def test_a_report_run_writes_nothing(source):
    before = (cs.UNITS_DIR / "u_bank.json").read_text(encoding="utf-8")

    ru.main([])

    assert (cs.UNITS_DIR / "u_bank.json").read_text(encoding="utf-8") == before


def test_the_report_counts_scope_both_ways(source, capsys):
    ru.main([])

    out = capsys.readouterr().out
    assert "Out-of-scope sentences now" in out
    assert "Out-of-scope sentences reordered" in out


def test_it_names_what_the_reorder_would_break(tmp_path, monkeypatch, capsys):
    """The measurement that makes this decision rather than a guess.

    A generated HSK 2 lesson written while the authored HSK 3 units came first
    may legitimately use their characters. Move it ahead of them and those
    sentences are out of scope — content that was correct, and paid for, when it
    was generated.
    """
    monkeypatch.setattr(cs, "CONTENT_DIR", tmp_path)
    monkeypatch.setattr(cs, "MANIFEST_PATH", tmp_path / "curriculum.json")
    monkeypatch.setattr(cs, "UNITS_DIR", tmp_path / "units")

    authored = _unit("u_bank", 3, 1, generated=False)
    authored["lessons"][0]["vocab"] = [
        {"id": "v_bank", "traditional": "銀行", "pinyin": "yínháng", "gloss": "bank"}
    ]
    # Generated HSK 2, currently taught after u_bank, leaning on its 銀行.
    later = _unit("u_hsk2_01", 2, 2, generated=True,
                  sentences=[{"tokens": ["銀行"], "pinyin": "p", "gloss": "g"}])
    cs.split({"meta": {"function_words": []}, "units": [authored, later]})

    ru.main([])

    out = capsys.readouterr().out
    assert "would fall OUT of scope" in out
    assert "銀" in out
