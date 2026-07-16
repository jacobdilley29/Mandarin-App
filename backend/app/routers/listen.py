"""Listen API (spec §3.3, §4).

GET  /api/listen/dictation        a dictation sentence (audio + target)
POST /api/listen/check            diff a dictation answer against the target
GET  /api/listen/sets             list available comprehension sets
GET  /api/listen/set              a comprehension set (dialogue + questions)
GET  /api/listen/tones            a tone ear-training item (single | pair)
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .. import listen, textdiff
from ..db import get_db

router = APIRouter(prefix="/api/listen", tags=["listen"])


@router.get("/dictation")
def get_dictation(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    item = listen.dictation_item(conn)
    if not item:
        raise HTTPException(404, "no dictation content available")
    return item


class DictationCheck(BaseModel):
    expected_hanzi: str
    expected_pinyin: str
    answer: str
    tone_sensitive: bool = True


@router.post("/check")
def check_dictation(body: DictationCheck) -> dict:
    return textdiff.dictation_check(
        body.expected_hanzi, body.expected_pinyin, body.answer, body.tone_sensitive
    )


@router.get("/sets")
def get_sets() -> dict:
    return {"sets": listen.list_sets()}


@router.get("/set")
def get_set(id: str | None = Query(default=None)) -> dict:
    item = listen.comprehension_set(id)
    if not item:
        raise HTTPException(404, "no comprehension sets available")
    return item


@router.get("/tones")
def get_tones(
    mode: str = Query(default="single", pattern="^(single|pair)$"),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    item = listen.tone_item(conn, mode)
    if not item:
        raise HTTPException(404, f"no tone content for mode={mode}")
    return item
