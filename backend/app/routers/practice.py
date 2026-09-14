"""Practice sessions — extra drilling that never touches the SRS schedule.

GET  /api/practice/needs    weak spots (spec §3.6)
GET  /api/practice/known    already-mastered items (spec §3.1)
POST /api/practice/result   log the session for the streak
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from .. import practice
from ..db import get_db

router = APIRouter(prefix="/api/practice", tags=["practice"])


@router.get("/needs")
def needs(
    limit: int = Query(practice.DEFAULT_SIZE, ge=1, le=50),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    return practice.needs_practice(conn, limit)


@router.get("/known")
def known(
    limit: int = Query(practice.DEFAULT_SIZE, ge=1, le=50),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    return practice.known_material(conn, limit)


class PracticeResult(BaseModel):
    answered: int = Field(ge=0)
    correct: int = Field(ge=0)


@router.post("/result")
def result(body: PracticeResult, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return practice.record_session(conn, body.answered, body.correct)
