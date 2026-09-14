"""TOCFL-first level labelling (spec §3.1)."""

from __future__ import annotations

import pytest

from app import levels


@pytest.mark.parametrize(
    "hsk, tocfl, cefr",
    [(1, "Novice", "pre-A1"), (2, "Level 1", "A1"), (3, "Level 2", "A2"), (4, "Level 3", "B1")],
)
def test_every_band_maps_to_tocfl_and_cefr(hsk, tocfl, cefr):
    b = levels.band(hsk)
    assert b["tocfl_level"] == tocfl and b["cefr"] == cefr


def test_tocfl_leads_and_hsk_trails():
    """The exam Jacob is working toward is the headline; HSK is the sourcing note."""
    b = levels.band(3)
    assert b["label"] == "Level 2"
    assert b["sublabel"] == "HSK 3"
    assert b["label_zh"] == "基礎級"


def test_jacobs_level_maps_where_expected():
    """A2/B1 is TOCFL Level 2–3 — i.e. HSK 3–4, which is what placement must reach."""
    assert levels.band(3)["cefr"] == "A2"
    assert levels.band(4)["cefr"] == "B1"


def test_an_unknown_level_renders_rather_than_raising():
    """A vocab item with no hsk_level should show a dash, not break a screen."""
    for missing in (None, 0, 99):
        b = levels.band(missing)
        assert b["label"] == "—"
        assert b["tocfl_level"] is None


def test_all_bands_are_ordered():
    assert [b["hsk_level"] for b in levels.all_bands()] == [1, 2, 3, 4]


def test_the_word_count_caveat_is_available_to_the_ui():
    """TOCFL's targets run ahead of HSK's, so the UI must say 'aligned to', not 'covers'."""
    c = levels.caveat()
    assert c and "aligned to" in c
