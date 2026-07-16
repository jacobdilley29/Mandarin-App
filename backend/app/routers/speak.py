"""Speak API (spec §3.4, §4).

POST /api/speak/score   multipart: audio (16-kHz mono WAV) + target text
                        → transcription, per-syllable tones, contour points
GET  /api/speak/item    a shadowing target (word or sentence)
GET  /api/speak/status  whether local transcription is available
"""

from __future__ import annotations

import random
import sqlite3

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from .. import speak, whisper_asr
from ..db import get_db

router = APIRouter(prefix="/api/speak", tags=["speak"])

MAX_AUDIO_BYTES = 5 * 1024 * 1024  # ~5 MB of 16-kHz WAV is plenty


@router.get("/status")
def status() -> dict:
    return {"transcription_available": whisper_asr.available()}


@router.get("/item")
def item(
    mode: str = Query(default="word", pattern="^(word|sentence)$"),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    if mode == "word":
        rows = conn.execute(
            "SELECT traditional AS hanzi, pinyin, gloss FROM vocab WHERE hsk_level IS NOT NULL"
        ).fetchall()
        pool = [dict(r) for r in rows]
    else:
        pool = []
        import json

        for lesson in conn.execute("SELECT sentences FROM lessons").fetchall():
            for s in json.loads(lesson["sentences"] or "[]"):
                hanzi = "".join(s.get("tokens", []))
                if hanzi and s.get("pinyin"):
                    pool.append({"hanzi": hanzi, "pinyin": s["pinyin"], "gloss": s.get("gloss", "")})
    if not pool:
        raise HTTPException(404, "no speak content available")
    it = random.choice(pool)
    return {"hanzi": it["hanzi"], "pinyin": it["pinyin"], "gloss": it.get("gloss", "")}


@router.post("/score")
async def score(
    audio: UploadFile = File(...),
    hanzi: str = Form(...),
    pinyin: str = Form(...),
) -> dict:
    data = await audio.read()
    if not data:
        raise HTTPException(422, "empty audio")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "audio too large")
    try:
        return speak.score(data, hanzi, pinyin)
    except ValueError as e:
        raise HTTPException(422, f"could not read audio: {e}")
