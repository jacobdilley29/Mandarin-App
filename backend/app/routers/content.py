"""Curriculum coverage reporting (spec §3.1).

"Track completeness explicitly ... so a half-populated level is visible rather
than silently passing as done." This is where that visibility lives: what is
being taught, what is staged as draft, and precisely what each draft is still
missing.
"""

from __future__ import annotations

import json
import sqlite3

from fastapi import APIRouter, Depends

from .. import completeness, curriculum_source
from ..db import get_db

router = APIRouter(prefix="/api/content", tags=["content"])


@router.get("/coverage")
def coverage() -> dict:
    """Per-unit completeness, computed from the curriculum source files."""
    return completeness.summary(curriculum_source.load())


@router.get("/coverage/db")
def coverage_db(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """The same, as actually loaded into the database.

    Worth having separately from the source view: a mismatch means the DB is
    stale relative to content/units/ and needs `scripts.load_content` re-run.
    """
    rows = conn.execute(
        "SELECT id, title, status, completeness FROM units ORDER BY sort_order"
    ).fetchall()
    units = []
    for r in rows:
        entry = {"unit_id": r["id"], "title": r["title"], "status": r["status"]}
        if r["completeness"]:
            entry.update(json.loads(r["completeness"]))
        units.append(entry)
    return {
        "units": len(units),
        "live": sum(1 for u in units if u["status"] == curriculum_source.STATUS_LIVE),
        "draft": sum(1 for u in units if u["status"] != curriculum_source.STATUS_LIVE),
        "report": units,
    }
