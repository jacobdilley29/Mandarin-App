"""Review + placement API (spec §3.2, §4).

GET  /api/review/queue            today's FSRS queue (rendered items)
POST /api/review/answer           {card_id, rating} → next schedule
GET  /api/review/stats            due/new/mature counts
GET  /api/placement               placement quiz items (first run)
POST /api/placement/result        seed deck from placement answers
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import review, srs
from ..db import get_db

router = APIRouter(prefix="/api", tags=["review"])


def _new_limit(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT daily_new_limit FROM settings WHERE id = 1").fetchone()
    return row["daily_new_limit"] if row else 15


@router.get("/review/queue")
def review_queue(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    items = review.build_queue(conn, _new_limit(conn))
    return {"items": items, "count": len(items)}


@router.get("/review/stats")
def review_stats(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return srs.counts(conn)


class ReviewAnswer(BaseModel):
    card_id: int
    rating: int = Field(ge=1, le=4)  # 1 Again .. 4 Easy
    elapsed_ms: int | None = None


@router.post("/review/answer")
def review_answer(body: ReviewAnswer, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    try:
        return srs.apply_review(conn, body.card_id, body.rating, body.elapsed_ms)
    except KeyError:
        raise HTTPException(404, "card not found")
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/placement")
def placement(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    done = conn.execute("SELECT placement_done FROM settings WHERE id = 1").fetchone()
    return {
        "done": bool(done and done["placement_done"]),
        "items": review.placement_items(conn),
    }


class PlacementItemResult(BaseModel):
    vocab_id: str
    correct: bool


class PlacementResultIn(BaseModel):
    results: list[PlacementItemResult] = []


@router.post("/placement/result")
def placement_result(body: PlacementResultIn, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return review.seed_placement(conn, [r.model_dump() for r in body.results])
