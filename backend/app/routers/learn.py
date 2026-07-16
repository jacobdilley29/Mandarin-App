"""Learn API — curriculum, lesson exercise stream, and result recording.

GET  /api/curriculum            units + lessons + completion/unlock state
GET  /api/lesson/{id}           built exercise stream for a lesson
POST /api/lesson/{id}/result    record answers → score, unlock logic, SRS enrol
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import content, exercises
from ..db import get_db

router = APIRouter(prefix="/api", tags=["learn"])


@router.get("/curriculum")
def get_curriculum(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return content.get_curriculum(conn)


@router.get("/lesson/{lesson_id}")
def get_lesson(lesson_id: str, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    lesson = content.get_lesson_content(conn, lesson_id)
    if not lesson:
        raise HTTPException(404, "lesson not found")

    pool = content.all_vocab(conn)
    stream = exercises.build_stream(lesson, pool)
    gradable = sum(1 for e in stream if e["gradable"])
    return {
        "id": lesson["id"],
        "title": lesson["title"],
        "unit_id": lesson["unit_id"],
        "unlocked": content.is_unlocked(conn, lesson_id),
        "gradable_count": gradable,
        "exercises": stream,
    }


class DrillResult(BaseModel):
    id: str
    kind: str
    correct: bool
    vocab_id: str | None = None
    grammar_id: str | None = None


class LessonResultIn(BaseModel):
    results: list[DrillResult] = []


@router.post("/lesson/{lesson_id}/result")
def post_result(
    lesson_id: str,
    body: LessonResultIn,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    lesson = content.get_lesson_content(conn, lesson_id)
    if not lesson:
        raise HTTPException(404, "lesson not found")

    gradable = [r for r in body.results if r.kind in exercises.GRADABLE_KINDS]
    total = len(gradable)
    correct = sum(1 for r in gradable if r.correct)
    score = (correct / total) if total else 0.0

    # Log drill errors so Progress can surface weak spots later.
    for r in gradable:
        if not r.correct and (r.vocab_id or r.grammar_id):
            conn.execute(
                """INSERT INTO drill_errors (grammar_id, vocab_id, detail)
                   VALUES (?, ?, ?)""",
                (r.grammar_id, r.vocab_id, r.kind),
            )
    conn.commit()

    outcome = content.record_result(conn, lesson_id, score)
    return {
        "score": score,
        "correct": correct,
        "total": total,
        **outcome,
    }
