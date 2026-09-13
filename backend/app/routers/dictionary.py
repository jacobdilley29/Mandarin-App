"""Word lookup while reading (spec §5).

Two endpoints, both read-only:

  POST /api/dictionary/annotate   a whole sentence -> tappable spans
  GET  /api/dictionary/{word}     one word, for anything that already has it

The annotate call is the one the reader uses: segmenting server-side, once per
sentence, keeps a tap instant instead of putting a request between the learner
and the word they are stuck on.
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import dictionary
from ..db import get_db

router = APIRouter(prefix="/api/dictionary", tags=["dictionary"])


class AnnotateIn(BaseModel):
    text: str = Field(max_length=2000)


@router.post("/annotate")
def annotate(body: AnnotateIn, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return {"spans": dictionary.annotate(conn, body.text)}


@router.get("/{word}")
def define(word: str, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    entry = dictionary.lookup(conn, word)
    if not entry:
        raise HTTPException(404, f"no entry for {word}")
    return entry
