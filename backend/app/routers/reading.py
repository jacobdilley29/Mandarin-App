"""Reading API (spec §3.2, §3.6).

GET  /api/reading            the library: unlocked, due, locked
GET  /api/reading/due        just what FSRS says to reread today
GET  /api/reading/{lesson_id}  one passage, with the words its lesson taught
POST /api/reading/answer     {lesson_id, rating} -> the passage's new schedule
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import reading
from ..db import get_db

router = APIRouter(prefix="/api/reading", tags=["reading"])


@router.get("")
def library(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return reading.library(conn)


@router.get("/due")
def due(limit: int = 10, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    items = reading.due(conn, limit)
    return {"passages": items, "count": len(items)}


class ReadingAnswer(BaseModel):
    lesson_id: str
    rating: int = Field(ge=1, le=4)  # 1 Again .. 4 Easy


@router.post("/answer")
def answer(body: ReadingAnswer, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    try:
        return reading.record_read(conn, body.lesson_id, body.rating)
    except KeyError:
        raise HTTPException(404, "no passage for that lesson")
    except PermissionError:
        raise HTTPException(403, "finish the lesson before reading its passage")
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/{lesson_id}")
def passage(lesson_id: str, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    found = reading.get_passage(conn, lesson_id)
    if not found:
        raise HTTPException(404, "no passage for that lesson")
    if not found["unlocked"]:
        raise HTTPException(403, "finish the lesson before reading its passage")
    return found
