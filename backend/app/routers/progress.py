"""Progress API (spec §3.6, §4).

GET /api/progress   dashboard stats (streak, activity, words by HSK, tone
                    accuracy, retention, weakest grammar).
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from .. import progress as progress_mod
from ..db import get_db

router = APIRouter(prefix="/api", tags=["progress"])


@router.get("/progress")
def get_progress(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return progress_mod.get_progress(conn)
