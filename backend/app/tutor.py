"""Ask-a-question tutor (spec §3.7).

A chat where Jacob asks about what he is studying — why a grammar point applies
here and not there, the difference between 才 and 就, whether a phrasing sounds
natural in Taipei. Distinct from the roleplay in conversation.py, which stays in
character and never explains itself; here explaining is the whole job.

What makes it worth having over a general chat window is the context: §3.7 asks
that "the tutor call should be given context about what Jacob is currently
working on (current unit/lesson, recently missed items) so answers reference the
actual curriculum rather than being generic". The app already records all of
that, so `_context()` assembles it from lesson progress, drill errors and SRS
lapses, and `focus` carries whatever he was looking at when the question
occurred to him.

Threads are stored in progress.db, because spec §7 lists tutor conversation
history among the data that must survive an app update and reach the backups.
They share the talk_* tables with roleplay, distinguished by kind='tutor'.
"""

from __future__ import annotations

import json
import sqlite3
import uuid

from . import conversation
from .llm import MODEL

KIND = "tutor"
MAX_HISTORY = 20  # turns kept in the prompt; the thread itself is never trimmed

SYSTEM_PROMPT = """\
You are a patient, precise teacher of Taiwanese Mandarin, answering a learner's \
questions about the language he is studying.

Who you are talking to: an intermediate learner (roughly TOCFL A2/B1) living in \
or oriented toward Taiwan. He reads Traditional characters and uses Hanyu pinyin, \
not Zhuyin.

How to answer:
- Explain in ENGLISH. The learner is asking because he wants to understand, so \
clarity beats immersion here.
- Write every Chinese example in TRADITIONAL characters with Taiwan vocabulary \
and Taiwan readings. Never simplified.
- Give 2-3 short example sentences that show the point in ordinary Taiwan usage — \
things he might actually hear or say — each with pinyin (tone marks) and an \
English gloss.
- When the question contrasts two things (才 vs 就, 會 vs 要, 的 vs 得), say \
plainly what decides which one, then show the contrast in a minimal pair.
- Where Taiwan usage differs from Mainland Mandarin, say so in taiwan_note. \
Leave it null when there is no real difference — inventing one is worse than \
staying quiet.
- Be direct and short. He asked a specific question; answer it. Do not open with \
praise or restate the question back to him.
- If the question is not about Mandarin, say so briefly rather than answering it.

You are given what he is currently studying. Prefer examples built from words he \
already knows, and when the question touches something in his curriculum, say so."""


# ---------------------------------------------------------------------------
# Context (spec §3.7)
# ---------------------------------------------------------------------------
def _current_position(conn: sqlite3.Connection) -> dict:
    """Where the learner is in the curriculum right now."""
    last = conn.execute(
        """SELECT l.id, l.title, u.title AS unit FROM lesson_progress p
           JOIN lessons l ON l.id = p.lesson_id
           JOIN units u ON u.id = l.unit_id
           WHERE p.completed = 1 ORDER BY p.completed_at DESC LIMIT 1"""
    ).fetchone()
    return {
        "last_completed": (
            {"lesson": last["title"], "unit": last["unit"]} if last else None
        ),
        "lessons_done": conn.execute(
            "SELECT COUNT(*) AS n FROM lesson_progress WHERE completed = 1"
        ).fetchone()["n"],
    }


def _recent_misses(conn: sqlite3.Connection, limit: int = 8) -> list[str]:
    """What he has been getting wrong — drill errors first, then SRS lapses."""
    misses: list[str] = []

    for r in conn.execute(
        """SELECT g.title FROM drill_errors d JOIN grammar g ON g.id = d.grammar_id
           WHERE d.grammar_id IS NOT NULL
           GROUP BY d.grammar_id ORDER BY COUNT(*) DESC LIMIT ?""",
        (limit,),
    ):
        misses.append(f"grammar: {r['title']}")

    for r in conn.execute(
        """SELECT v.traditional, v.gloss, c.lapses FROM srs_cards c
           JOIN vocab v ON v.id = c.item_id
           WHERE c.item_type = 'vocab' AND c.lapses > 0
           ORDER BY c.lapses DESC LIMIT ?""",
        (limit,),
    ):
        misses.append(f"{r['traditional']} ({r['gloss']}) — forgotten {r['lapses']}x")

    return misses[:limit]


def _focus_line(conn: sqlite3.Connection, focus: dict | None) -> str | None:
    """The thing he was looking at when the question came up.

    `focus` is {type: 'vocab'|'grammar'|'sentence', id or text}. Looked up rather
    than trusted, so the prompt describes real curriculum rather than whatever
    the client happened to send.
    """
    if not focus:
        return None
    kind, ident = focus.get("type"), focus.get("id")

    if kind == "vocab" and ident:
        r = conn.execute(
            "SELECT traditional, pinyin, gloss FROM vocab WHERE id = ?", (ident,)
        ).fetchone()
        if r:
            return f"He is looking at the word {r['traditional']} ({r['pinyin']}) — {r['gloss']}."
    if kind == "grammar" and ident:
        r = conn.execute(
            "SELECT title, pattern, explanation FROM grammar WHERE id = ?", (ident,)
        ).fetchone()
        if r:
            return (
                f"He is looking at the grammar point {r['title']} "
                f"(pattern: {r['pattern']}) — {r['explanation']}"
            )
    if text := (focus.get("text") or "").strip():
        return f"He is looking at this sentence: {text}"
    return None


def _context(conn: sqlite3.Connection, focus: dict | None = None) -> str:
    position = _current_position(conn)
    misses = _recent_misses(conn)
    known = conversation.known_words_summary(conn)

    parts = [f"Lessons completed so far: {position['lessons_done']}."]
    if position["last_completed"]:
        lc = position["last_completed"]
        parts.append(f"Most recently finished: {lc['lesson']} (unit: {lc['unit']}).")
    if line := _focus_line(conn, focus):
        parts.append(line)
    if misses:
        parts.append("Recently getting wrong: " + "; ".join(misses) + ".")
    if known:
        parts.append(f"Words he knows include: {known}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Threads (spec §7 — this is progress data)
# ---------------------------------------------------------------------------
def start_thread(conn: sqlite3.Connection) -> str:
    thread_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO talk_sessions (id, scenario, kind) VALUES (?, 'tutor', ?)",
        (thread_id, KIND),
    )
    conn.commit()
    return thread_id


def history(conn: sqlite3.Connection, thread_id: str) -> list[dict]:
    rows = conn.execute(
        """SELECT role, content, payload FROM talk_messages
           WHERE session_id = ? ORDER BY id""",
        (thread_id,),
    ).fetchall()
    return [
        {
            "role": r["role"],
            "content": r["content"],
            **(json.loads(r["payload"]) if r["payload"] else {}),
        }
        for r in rows
    ]


def threads(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        """SELECT s.id, s.created_at,
                  (SELECT content FROM talk_messages m
                    WHERE m.session_id = s.id AND m.role = 'user'
                    ORDER BY m.id LIMIT 1) AS opening
           FROM talk_sessions s WHERE s.kind = ?
           ORDER BY s.created_at DESC LIMIT ?""",
        (KIND, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def _record(
    conn: sqlite3.Connection, thread_id: str, role: str, content: str, payload: dict | None = None
) -> None:
    conn.execute(
        """INSERT INTO talk_messages (session_id, role, content, payload)
           VALUES (?, ?, ?, ?)""",
        (thread_id, role, content, json.dumps(payload, ensure_ascii=False) if payload else None),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Asking
# ---------------------------------------------------------------------------
def available(conn: sqlite3.Connection | None = None) -> bool:
    """Same requirement as Talk: a key and the SDK."""
    return conversation.available(conn)


def _models():
    from pydantic import BaseModel

    class Example(BaseModel):
        hanzi: str
        pinyin: str
        gloss: str

    class Answer(BaseModel):
        answer: str
        examples: list[Example]
        taiwan_note: str | None
        related: list[str]

    return Answer


def ask(
    conn: sqlite3.Connection,
    question: str,
    focus: dict | None = None,
    thread_id: str | None = None,
    client=None,
) -> dict:
    """Answer one question. Raises RuntimeError when the tutor is unavailable.

    `client` is injectable so the whole path can be tested without spending
    anything or needing a key.
    """
    question = (question or "").strip()
    if not question:
        raise ValueError("empty question")

    if client is None:
        key = conversation.effective_api_key(conn)
        if not key:
            raise RuntimeError("tutor unavailable (no Anthropic API key)")
        try:
            import anthropic
        except ImportError:
            raise RuntimeError("tutor unavailable (anthropic package not installed)")
        client = anthropic.Anthropic(api_key=key)

    if thread_id is None:
        thread_id = start_thread(conn)

    prior = history(conn, thread_id)[-MAX_HISTORY:]
    messages = [{"role": m["role"], "content": m["content"]} for m in prior]
    messages.append({"role": "user", "content": question})

    Answer = _models()
    response = client.messages.parse(
        model=MODEL,
        max_tokens=2000,
        thinking={"type": "adaptive"},
        system=f"{SYSTEM_PROMPT}\n\nWhat he is currently studying:\n{_context(conn, focus)}",
        messages=messages,
        output_format=Answer,
    )
    answer = response.parsed_output
    if answer is None:
        raise RuntimeError("model returned no parsable answer")

    result = answer.model_dump()
    _record(conn, thread_id, "user", question, {"focus": focus} if focus else None)
    _record(conn, thread_id, "assistant", result["answer"], result)
    return {"thread_id": thread_id, **result}
