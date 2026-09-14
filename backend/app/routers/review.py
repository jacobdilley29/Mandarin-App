"""Review + placement API (spec §3.2, §4).

GET  /api/review/queue            today's FSRS queue (rendered items)
POST /api/review/answer           {card_id, rating} → next schedule
GET  /api/review/stats            due/new/mature counts
GET  /api/placement               start the adaptive placement check
POST /api/placement/round         score one band → next round, or the summary
POST /api/placement/result        finish from a flat list of answers
GET  /api/placement/summary       band verdicts + where to start
POST /api/placement/reset         retake it (keeps SRS history)
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import levels, placement as placement_mod, review, srs
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
    """Start the placement check: the first band's round.

    Adaptive, so the client plays one band at a time and posts each round back;
    the server decides where to go next. See app/placement.py.
    """
    done = conn.execute("SELECT placement_done FROM settings WHERE id = 1").fetchone()
    return {
        "done": bool(done and done["placement_done"]),
        "start_band": placement_mod.START_BAND,
        "bands": placement_mod.band_states(conn),
        "round": placement_mod.build_round(conn, placement_mod.START_BAND),
    }


class PlacementItemResult(BaseModel):
    vocab_id: str | None = None
    correct: bool


class PlacementRoundIn(BaseModel):
    band: int
    results: list[PlacementItemResult] = []
    # Bands already answered, so the walk can't loop between two of them.
    visited: list[int] = []
    # Vocab already asked, so a later round doesn't repeat a word.
    seen: list[str] = []


@router.post("/placement/round")
def placement_round(body: PlacementRoundIn, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Score one band and hand back the next round, or the final summary."""
    if body.band not in levels.BANDS:
        raise HTTPException(422, f"unknown band {body.band}")

    outcome = placement_mod.record_round(
        conn, body.band, [r.model_dump() for r in body.results]
    )
    visited = set(body.visited) | {body.band}
    nxt = placement_mod.next_band(body.band, outcome["status"], visited)

    if nxt is None:
        return {"outcome": outcome, "done": True, "summary": placement_mod.finalize(conn)}

    return {
        "outcome": outcome,
        "done": False,
        "round": placement_mod.build_round(conn, nxt, seen=set(body.seen)),
        "visited": sorted(visited),
    }


class PlacementItemResultLegacy(BaseModel):
    vocab_id: str
    correct: bool


class PlacementResultIn(BaseModel):
    results: list[PlacementItemResultLegacy] = []


@router.post("/placement/result")
def placement_result(body: PlacementResultIn, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Finish placement from a flat list of results.

    Kept for the single-round path and for a client that wants to submit
    everything at once; the adaptive flow uses /placement/round.
    """
    placement_mod.record_round(conn, placement_mod.START_BAND, [r.model_dump() for r in body.results])
    return placement_mod.finalize(conn)


@router.get("/placement/summary")
def placement_summary(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return placement_mod.summary(conn)


@router.post("/placement/reset")
def placement_reset(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    """Retake the check. SRS cards are kept — that's real review history."""
    placement_mod.reset(conn)
    return {"done": False}
