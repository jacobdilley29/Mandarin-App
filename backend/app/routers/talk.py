"""Talk API (spec §3.5, §4).

GET  /api/talk/scenarios          available roleplay scenarios
POST /api/talk/start              start a session → opening line
POST /api/talk/message            a conversation turn (server holds history)
POST /api/talk/transcribe         mic (WAV) → text (speak input; optional)
GET  /api/talk/recap/{id}         new words encountered → add-to-SRS candidates
POST /api/talk/recap/add          add chosen words to the SRS deck
"""

from __future__ import annotations

import json
import sqlite3
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from .. import conversation, pitch, speak, srs, whisper_asr
from ..db import get_db

router = APIRouter(prefix="/api/talk", tags=["talk"])


@router.get("/scenarios")
def scenarios() -> dict:
    return {
        "available": conversation.available(),
        "scenarios": [
            {"id": s["id"], "emoji": s["emoji"], "title": s["title"], "en": s["en"], "opening": s["opening"]}
            for s in conversation.SCENARIOS
        ],
    }


class StartIn(BaseModel):
    scenario: str


@router.post("/start")
def start(body: StartIn, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    sc = conversation.scenario(body.scenario)
    if not sc:
        raise HTTPException(404, "unknown scenario")
    session_id = uuid.uuid4().hex
    conn.execute("INSERT INTO talk_sessions (id, scenario) VALUES (?, ?)", (session_id, body.scenario))
    # Store the canned opening as the first assistant turn.
    meta = {"reply_pinyin": sc["opening"]["pinyin"], "teacher_note": None, "new_words": []}
    conn.execute(
        "INSERT INTO talk_messages (session_id, role, content, teacher_note) VALUES (?, 'assistant', ?, ?)",
        (session_id, sc["opening"]["hanzi"], json.dumps(meta, ensure_ascii=False)),
    )
    conn.commit()
    return {
        "session_id": session_id,
        "scenario": {"id": sc["id"], "title": sc["title"], "en": sc["en"], "emoji": sc["emoji"]},
        "opening": {**sc["opening"]},
    }


class MessageIn(BaseModel):
    session_id: str
    text: str


@router.post("/message")
def message(body: MessageIn, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    sess = conn.execute("SELECT scenario FROM talk_sessions WHERE id = ?", (body.session_id,)).fetchone()
    if not sess:
        raise HTTPException(404, "unknown session")
    if not conversation.available():
        raise HTTPException(503, "conversation unavailable — set ANTHROPIC_API_KEY")

    history = [
        {"role": r["role"], "content": r["content"]}
        for r in conn.execute(
            "SELECT role, content FROM talk_messages WHERE session_id = ? ORDER BY id", (body.session_id,)
        ).fetchall()
    ]
    conn.execute(
        "INSERT INTO talk_messages (session_id, role, content) VALUES (?, 'user', ?)",
        (body.session_id, body.text),
    )
    try:
        turn = conversation.reply(conn, sess["scenario"], history, body.text)
    except RuntimeError as e:
        raise HTTPException(503, str(e))

    meta = {
        "reply_pinyin": turn["reply_pinyin"],
        "teacher_note": turn["teacher_note"],
        "new_words": turn["new_words"],
    }
    conn.execute(
        "INSERT INTO talk_messages (session_id, role, content, teacher_note) VALUES (?, 'assistant', ?, ?)",
        (body.session_id, turn["reply"], json.dumps(meta, ensure_ascii=False)),
    )
    conn.commit()
    return turn


@router.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)) -> dict:
    if not whisper_asr.available():
        raise HTTPException(503, "transcription unavailable — install faster-whisper")
    data = await audio.read()
    try:
        samples, sr = pitch.read_wav(data)
    except ValueError as e:
        raise HTTPException(422, f"could not read audio: {e}")
    result = whisper_asr.transcribe(speak._resample_16k(samples, sr))
    return {"text": result["text"] if result else ""}


@router.get("/recap/{session_id}")
def recap(session_id: str, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    rows = conn.execute(
        "SELECT teacher_note FROM talk_messages WHERE session_id = ? AND role='assistant'",
        (session_id,),
    ).fetchall()
    seen: dict[str, dict] = {}
    for r in rows:
        meta = json.loads(r["teacher_note"] or "{}")
        for w in meta.get("new_words", []):
            if w.get("hanzi") and w["hanzi"] not in seen:
                seen[w["hanzi"]] = w
    words = []
    for hanzi, w in seen.items():
        exists = conn.execute(
            """SELECT 1 FROM vocab v JOIN srs_cards c ON c.item_id = v.id
               WHERE v.traditional = ? AND c.item_type='vocab'""",
            (hanzi,),
        ).fetchone()
        words.append({**w, "in_deck": bool(exists)})
    return {"words": words}


class RecapAddIn(BaseModel):
    words: list[dict]  # [{hanzi, pinyin, gloss}]


@router.post("/recap/add")
def recap_add(body: RecapAddIn, conn: sqlite3.Connection = Depends(get_db)) -> dict:
    added = 0
    for w in body.words:
        hanzi = w.get("hanzi")
        if not hanzi:
            continue
        row = conn.execute("SELECT id FROM vocab WHERE traditional = ?", (hanzi,)).fetchone()
        if row:
            vid = row["id"]
        else:
            vid = "tk_" + uuid.uuid4().hex[:10]
            conn.execute(
                "INSERT INTO vocab (id, traditional, pinyin, gloss) VALUES (?, ?, ?, ?)",
                (vid, hanzi, w.get("pinyin", ""), w.get("gloss", "")),
            )
        before = conn.execute(
            "SELECT 1 FROM srs_cards WHERE item_type='vocab' AND item_id=? AND card_type='recognition'",
            (vid,),
        ).fetchone()
        srs.ensure_new_card(conn, "vocab", vid, "recognition")
        if not before:
            added += 1
    conn.commit()
    return {"added": added}
