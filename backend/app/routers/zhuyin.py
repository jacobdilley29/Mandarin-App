"""注音 course API (spec §3.1, adapted).

GET  /api/zhuyin/course             the lesson list, with progress
GET  /api/zhuyin/lesson/{id}        one lesson's exercise stream
POST /api/zhuyin/lesson/{id}/result score an attempt, enrol symbols in the SRS

The course is hand-authored content (content/zhuyin.json) rather than
curriculum, so it has its own router rather than riding on /api/learn: the
curriculum endpoints read the database, and there is nothing about 注音 in it.
Reviews, on the other hand, go through the ordinary queue — see
app/zhuyin_course.py for why.
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import zhuyin_course
from ..db import get_db

router = APIRouter(prefix="/api/zhuyin", tags=["zhuyin"])


@router.get("/course")
def get_course(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return zhuyin_course.course(conn)


@router.get("/lesson/{lesson_id}")
def get_lesson(lesson_id: str, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    lesson = zhuyin_course.get_lesson(conn, lesson_id)
    if not lesson:
        raise HTTPException(404, "lesson not found")
    return lesson


class SymbolResult(BaseModel):
    symbol: str
    correct: bool


class LessonResultIn(BaseModel):
    results: list[SymbolResult] = []


@router.post("/lesson/{lesson_id}/result")
def post_result(
    lesson_id: str,
    body: LessonResultIn,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    try:
        return zhuyin_course.record(
            conn, lesson_id, [r.model_dump() for r in body.results]
        )
    except KeyError:
        raise HTTPException(404, "lesson not found")
