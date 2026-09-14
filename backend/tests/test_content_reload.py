"""The database follows content/units/ (spec §3.1, §7).

This file exists because of a silent, expensive failure. A whole curriculum was
generated, committed, and baked into a rebuilt image — three times over — and the
app showed none of it. `ensure_loaded` only read the source when the `units`
table was empty, so after the first boot the database never looked at content/
again. No error, no warning, nothing to debug: the app simply served the old
curriculum forever.

The reason it is safe to reload every time is the two-database split. Content is
derived data and can be rebuilt from source; progress is not and cannot. These
tests pin that boundary, because reloading content would be a catastrophe if it
ever started touching the other side of it.
"""

from __future__ import annotations

import json

import pytest

from app import content, curriculum_source as cs, srs

from .conftest import attached_conn


def _unit(unit_id: str, title: str, *, finished: bool = True) -> dict:
    lesson = {
        "id": f"l_{unit_id}", "title": "L", "sort_order": 1,
        "vocab": [{"id": "v_yyk", "traditional": "悠遊卡", "pinyin": "yōuyóukǎ",
                   "gloss": "EasyCard", "hsk_level": 1,
                   "example": {"hanzi": "悠遊卡", "pinyin": "p", "gloss": "g"}}],
        "grammar": [{"id": "g1", "title": "t", "pattern": "p", "explanation": "e",
                     "examples": []}] if finished else [],
        "sentences": [{"tokens": ["悠遊卡"]}] if finished else [],
        "dialogue": [{"hanzi": "悠遊卡"}] if finished else [],
    }
    return {"id": unit_id, "title": title, "sort_order": 1, "hsk_level": 1,
            "generated": True, "status": "live", "lessons": [lesson]}


@pytest.fixture
def source(tmp_path, monkeypatch):
    """A content/ directory the test can rewrite between 'restarts'."""
    monkeypatch.setattr(cs, "CONTENT_DIR", tmp_path)
    monkeypatch.setattr(cs, "MANIFEST_PATH", tmp_path / "curriculum.json")
    monkeypatch.setattr(cs, "UNITS_DIR", tmp_path / "units")

    def write(*units):
        cs.split({"meta": {"function_words": []}, "units": list(units)})

    write(_unit("u_one", "便利商店"))
    return write


@pytest.fixture
def db(tmp_path):
    d = tmp_path / "db"
    d.mkdir()
    c = attached_conn(d)
    yield c
    c.close()


def titles(conn) -> list[str]:
    return [r["title"] for r in conn.execute("SELECT title FROM units ORDER BY id")]


# ---------------------------------------------------------------------------
# The bug
# ---------------------------------------------------------------------------
def test_changed_content_reaches_the_app_on_restart(db, source):
    """Generate, commit, rebuild — and see it. That was not true before."""
    content.ensure_loaded(db)
    assert titles(db) == ["便利商店"]

    source(_unit("u_one", "夜市小吃"), _unit("u_two", "搭捷運"))
    content.ensure_loaded(db)  # the restart

    assert titles(db) == ["夜市小吃", "搭捷運"]


def test_a_first_boot_still_seeds_from_nothing(db, source):
    assert db.execute("SELECT COUNT(*) AS n FROM units").fetchone()["n"] == 0

    content.ensure_loaded(db)

    assert titles(db) == ["便利商店"]


# ---------------------------------------------------------------------------
# The boundary that makes reloading safe
# ---------------------------------------------------------------------------
def test_reloading_content_does_not_disturb_progress(db, source):
    """The whole justification for doing this on every startup.

    Content is derived from content/units/ and can be rebuilt at will. Progress
    is the one thing in this app that cannot be regenerated, which is why it
    lives in its own database (spec §7). If a content reload ever starts moving
    an SRS card, this test is the one that should fail.
    """
    content.ensure_loaded(db)
    card = srs.seed_mature(db, "vocab", "v_yyk")
    db.execute(
        """INSERT INTO lesson_progress (lesson_id, completed, best_score, unlocked)
           VALUES ('l_u_one', 1, 0.95, 1)"""
    )
    db.commit()
    before = tuple(db.execute("SELECT * FROM srs_cards WHERE id = ?", (card,)).fetchone())
    progress_before = tuple(
        db.execute("SELECT * FROM lesson_progress WHERE lesson_id = 'l_u_one'").fetchone()
    )

    source(_unit("u_one", "夜市小吃"), _unit("u_two", "搭捷運"))
    content.ensure_loaded(db)

    assert tuple(db.execute("SELECT * FROM srs_cards WHERE id = ?", (card,)).fetchone()) == before
    assert tuple(
        db.execute("SELECT * FROM lesson_progress WHERE lesson_id = 'l_u_one'").fetchone()
    ) == progress_before


def test_an_unfinished_unit_still_loads_as_a_draft(db, source):
    """Reloading must never promote content the completeness gate rejects."""
    source(_unit("u_one", "未完成", finished=False))

    content.ensure_loaded(db)

    row = db.execute("SELECT status FROM units WHERE id = 'u_one'").fetchone()
    assert row["status"] == "draft"


# ---------------------------------------------------------------------------
# A broken source must not take the app down
# ---------------------------------------------------------------------------
def test_a_broken_source_leaves_the_last_good_content_serving(db, source, caplog):
    """Startup runs this. A half-written file must not stop the app booting."""
    content.ensure_loaded(db)
    assert titles(db) == ["便利商店"]

    (cs.UNITS_DIR / "u_one.json").write_text("{ not json", encoding="utf-8")
    with caplog.at_level("WARNING"):
        content.ensure_loaded(db)  # must not raise

    assert titles(db) == ["便利商店"], "the previously loaded content still serves"
    assert "previously loaded" in caplog.text


def test_the_load_is_reported(db, source, caplog):
    """'Did my content land' should be answerable from the logs."""
    with caplog.at_level("INFO"):
        content.ensure_loaded(db)

    assert "1 live" in caplog.text
