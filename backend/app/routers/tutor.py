"""Ask-a-question tutor API (spec §3.7).

GET  /api/tutor/status     is it available, and recent threads
POST /api/tutor/ask        ask a question (optionally about a specific item)
GET  /api/tutor/thread/{id}  read a thread back
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import tutor
from ..db import get_db

router = APIRouter(prefix="/api/tutor", tags=["tutor"])


class Focus(BaseModel):
    """What the learner was looking at when the question came up."""

    type: str | None = None  # vocab | grammar | sentence
    id: str | None = None
    text: str | None = None


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    focus: Focus | None = None
    thread_id: str | None = None


@router.get("/status")
def status(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return {
        "available": tutor.available(conn),
        "threads": tutor.threads(conn),
    }


@router.post("/ask")
def ask(body: AskIn, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    try:
        return tutor.ask(
            conn,
            body.question,
            focus=body.focus.model_dump() if body.focus else None,
            thread_id=body.thread_id,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        # No key, or the SDK is missing: a disabled feature, not a server fault.
        raise HTTPException(503, str(exc)) from exc


@router.get("/thread/{thread_id}")
def thread(thread_id: str, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    messages = tutor.history(conn, thread_id)
    if not messages:
        raise HTTPException(404, "thread not found")
    return {"thread_id": thread_id, "messages": messages}
