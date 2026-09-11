"""Curriculum content: loading JSON into SQLite and reading it back.

The seed content lives in content/curriculum.json (repo root). It is loaded into
the DB at setup (scripts/load_content.py) and also, for convenience, on first
startup if the curriculum tables are empty.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .config import REPO_ROOT

CONTENT_PATH = REPO_ROOT / "content" / "curriculum.json"
HSK1_PATH = REPO_ROOT / "content" / "hsk1.json"

# Passing score to complete a lesson and unlock the next (spec §3.1).
PASS_THRESHOLD = 0.8


def _upsert_vocab(conn: sqlite3.Connection, v: dict) -> None:
    ex = v.get("example") or {}
    conn.execute(
        """INSERT INTO vocab
             (id, traditional, pinyin, gloss, hsk_level, taiwan_note,
              example_hanzi, example_pinyin, example_gloss)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             traditional=excluded.traditional, pinyin=excluded.pinyin,
             gloss=excluded.gloss, hsk_level=excluded.hsk_level,
             taiwan_note=excluded.taiwan_note,
             example_hanzi=excluded.example_hanzi,
             example_pinyin=excluded.example_pinyin,
             example_gloss=excluded.example_gloss""",
        (v["id"], v["traditional"], v["pinyin"], v["gloss"],
         v.get("hsk_level"), v.get("taiwan_note"),
         ex.get("hanzi"), ex.get("pinyin"), ex.get("gloss")),
    )


def load_vocab_list(conn: sqlite3.Connection, data: dict) -> int:
    """Load a flat vocabulary list (no lessons) — e.g. the HSK 1 placement pool."""
    vocab = data.get("vocab", [])
    for v in vocab:
        _upsert_vocab(conn, v)
    conn.commit()
    return len(vocab)


def load_hsk1_from_disk(conn: sqlite3.Connection) -> int | None:
    if not HSK1_PATH.is_file():
        return None
    data = json.loads(HSK1_PATH.read_text(encoding="utf-8"))
    return load_vocab_list(conn, data)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_curriculum(conn: sqlite3.Connection, data: dict) -> dict:
    """Upsert a curriculum JSON payload into the DB. Idempotent.

    Returns a small summary dict (counts) for logging.
    """
    units = data.get("units", [])
    n_lessons = n_vocab = n_grammar = 0

    for unit in units:
        conn.execute(
            """INSERT INTO units (id, title, subtitle, hsk_level, sort_order)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 title=excluded.title, subtitle=excluded.subtitle,
                 hsk_level=excluded.hsk_level, sort_order=excluded.sort_order""",
            (unit["id"], unit["title"], unit.get("subtitle"),
             unit.get("hsk_level"), unit.get("sort_order", 0)),
        )

        for lesson in unit.get("lessons", []):
            n_lessons += 1
            conn.execute(
                """INSERT INTO lessons (id, unit_id, title, sort_order, dialogue, sentences)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET
                     unit_id=excluded.unit_id, title=excluded.title,
                     sort_order=excluded.sort_order, dialogue=excluded.dialogue,
                     sentences=excluded.sentences""",
                (lesson["id"], unit["id"], lesson["title"],
                 lesson.get("sort_order", 0),
                 json.dumps(lesson.get("dialogue", []), ensure_ascii=False),
                 json.dumps(lesson.get("sentences", []), ensure_ascii=False)),
            )

            for i, v in enumerate(lesson.get("vocab", [])):
                n_vocab += 1
                _upsert_vocab(conn, v)
                conn.execute(
                    """INSERT INTO lesson_vocab (lesson_id, vocab_id, sort_order)
                       VALUES (?, ?, ?) ON CONFLICT DO NOTHING""",
                    (lesson["id"], v["id"], i),
                )

            for i, g in enumerate(lesson.get("grammar", [])):
                n_grammar += 1
                conn.execute(
                    """INSERT INTO grammar
                         (id, title, pattern, explanation, examples, hsk_level, sort_order)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET
                         title=excluded.title, pattern=excluded.pattern,
                         explanation=excluded.explanation, examples=excluded.examples,
                         hsk_level=excluded.hsk_level, sort_order=excluded.sort_order""",
                    (g["id"], g["title"], g["pattern"], g["explanation"],
                     json.dumps(g.get("examples", []), ensure_ascii=False),
                     g.get("hsk_level"), i),
                )
                conn.execute(
                    """INSERT INTO lesson_grammar (lesson_id, grammar_id, sort_order)
                       VALUES (?, ?, ?) ON CONFLICT DO NOTHING""",
                    (lesson["id"], g["id"], i),
                )

    conn.commit()
    return {"units": len(units), "lessons": n_lessons,
            "vocab": n_vocab, "grammar": n_grammar}


def load_from_disk(conn: sqlite3.Connection) -> dict | None:
    if not CONTENT_PATH.is_file():
        return None
    data = json.loads(CONTENT_PATH.read_text(encoding="utf-8"))
    return load_curriculum(conn, data)


def ensure_loaded(conn: sqlite3.Connection) -> None:
    """Load content on startup if the curriculum is empty."""
    row = conn.execute("SELECT COUNT(*) AS n FROM units").fetchone()
    if row["n"] == 0:
        load_from_disk(conn)
    # Load the HSK 1 placement pool if its foundation items aren't present yet.
    row = conn.execute("SELECT COUNT(*) AS n FROM vocab WHERE id LIKE 'h\\_%' ESCAPE '\\'").fetchone()
    if row["n"] == 0:
        load_hsk1_from_disk(conn)


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def _ordered_lessons(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT l.id, l.unit_id, l.title, l.sort_order
           FROM lessons l JOIN units u ON u.id = l.unit_id
           ORDER BY u.sort_order, l.sort_order"""
    ).fetchall()


def _progress_map(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    rows = conn.execute("SELECT * FROM lesson_progress").fetchall()
    return {r["lesson_id"]: r for r in rows}


def get_curriculum(conn: sqlite3.Connection) -> dict:
    """Units + lessons + per-lesson completion / unlock state.

    Unlock rule (spec §3.1): the first lesson in curriculum order is always
    unlocked; every other lesson unlocks once the lesson before it is completed.
    """
    order = _ordered_lessons(conn)
    progress = _progress_map(conn)

    unlocked: dict[str, bool] = {}
    prev_completed = True  # first lesson unlocked
    for row in order:
        lid = row["id"]
        unlocked[lid] = prev_completed
        p = progress.get(lid)
        prev_completed = bool(p and p["completed"])

    units = conn.execute(
        "SELECT * FROM units ORDER BY sort_order"
    ).fetchall()

    out_units = []
    for u in units:
        lessons = conn.execute(
            "SELECT * FROM lessons WHERE unit_id = ? ORDER BY sort_order",
            (u["id"],),
        ).fetchall()
        out_lessons = []
        for l in lessons:
            p = progress.get(l["id"])
            n_vocab = conn.execute(
                "SELECT COUNT(*) AS n FROM lesson_vocab WHERE lesson_id = ?",
                (l["id"],),
            ).fetchone()["n"]
            out_lessons.append({
                "id": l["id"],
                "title": l["title"],
                "vocab_count": n_vocab,
                "completed": bool(p and p["completed"]),
                "best_score": (p["best_score"] if p else None),
                "unlocked": unlocked.get(l["id"], False),
            })
        out_units.append({
            "id": u["id"],
            "title": u["title"],
            "subtitle": u["subtitle"],
            "hsk_level": u["hsk_level"],
            "lessons": out_lessons,
        })
    return {"units": out_units}


def is_unlocked(conn: sqlite3.Connection, lesson_id: str) -> bool:
    order = _ordered_lessons(conn)
    progress = _progress_map(conn)
    prev_completed = True
    for row in order:
        if row["id"] == lesson_id:
            return prev_completed
        p = progress.get(row["id"])
        prev_completed = bool(p and p["completed"])
    return False


def get_lesson_content(conn: sqlite3.Connection, lesson_id: str) -> dict | None:
    """Full raw content for a lesson: vocab, grammar, dialogue, sentences."""
    lesson = conn.execute(
        "SELECT * FROM lessons WHERE id = ?", (lesson_id,)
    ).fetchone()
    if not lesson:
        return None

    vocab = conn.execute(
        """SELECT v.* FROM vocab v
           JOIN lesson_vocab lv ON lv.vocab_id = v.id
           WHERE lv.lesson_id = ? ORDER BY lv.sort_order""",
        (lesson_id,),
    ).fetchall()
    grammar = conn.execute(
        """SELECT g.* FROM grammar g
           JOIN lesson_grammar lg ON lg.grammar_id = g.id
           WHERE lg.lesson_id = ? ORDER BY lg.sort_order""",
        (lesson_id,),
    ).fetchall()

    return {
        "id": lesson["id"],
        "unit_id": lesson["unit_id"],
        "title": lesson["title"],
        "vocab": [_vocab_dict(v) for v in vocab],
        "grammar": [_grammar_dict(g) for g in grammar],
        "dialogue": json.loads(lesson["dialogue"] or "[]"),
        "sentences": json.loads(lesson["sentences"] or "[]"),
    }


def _vocab_dict(v: sqlite3.Row) -> dict:
    return {
        "id": v["id"],
        "traditional": v["traditional"],
        "pinyin": v["pinyin"],
        "gloss": v["gloss"],
        "hsk_level": v["hsk_level"],
        "taiwan_note": v["taiwan_note"],
        "example": {
            "hanzi": v["example_hanzi"],
            "pinyin": v["example_pinyin"],
            "gloss": v["example_gloss"],
        } if v["example_hanzi"] else None,
    }


def _grammar_dict(g: sqlite3.Row) -> dict:
    return {
        "id": g["id"],
        "title": g["title"],
        "pattern": g["pattern"],
        "explanation": g["explanation"],
        "examples": json.loads(g["examples"] or "[]"),
        "hsk_level": g["hsk_level"],
    }


def all_vocab(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM vocab").fetchall()
    return [_vocab_dict(v) for v in rows]


# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------
def record_result(conn: sqlite3.Connection, lesson_id: str, score: float) -> dict:
    """Record a lesson attempt; mark complete + enrol vocab in SRS on a pass.

    Returns {passed, completed, best_score, unlocked_next, new_srs_cards}.
    """
    passed = score >= PASS_THRESHOLD

    existing = conn.execute(
        "SELECT * FROM lesson_progress WHERE lesson_id = ?", (lesson_id,)
    ).fetchone()
    prev_best = existing["best_score"] if existing and existing["best_score"] is not None else 0.0
    prev_completed = bool(existing and existing["completed"])
    best = max(prev_best, score)
    completed = prev_completed or passed

    conn.execute(
        """INSERT INTO lesson_progress (lesson_id, completed, best_score, unlocked, completed_at)
           VALUES (?, ?, ?, 1, CASE WHEN ? THEN datetime('now') ELSE NULL END)
           ON CONFLICT(lesson_id) DO UPDATE SET
             completed=excluded.completed, best_score=excluded.best_score,
             completed_at=COALESCE(lesson_progress.completed_at, excluded.completed_at)""",
        (lesson_id, int(completed), best, passed),
    )

    new_cards = 0
    if passed and not prev_completed:
        new_cards = _enrol_vocab_srs(conn, lesson_id)

    from . import progress

    progress.record_activity(
        conn, lessons=1 if passed else 0, minutes=progress.lesson_minutes()
    )
    conn.commit()

    # Find the next lesson in curriculum order to report unlock.
    order = _ordered_lessons(conn)
    unlocked_next = None
    for i, row in enumerate(order):
        if row["id"] == lesson_id and i + 1 < len(order):
            unlocked_next = order[i + 1]["id"] if completed else None
            break

    return {
        "passed": passed,
        "completed": completed,
        "best_score": best,
        "unlocked_next": unlocked_next,
        "new_srs_cards": new_cards,
    }


def _enrol_vocab_srs(conn: sqlite3.Connection, lesson_id: str) -> int:
    """Add this lesson's vocab to the SRS deck as new cards (spec §3.1).

    Creates a 'recognition' card per vocab item if one doesn't exist yet. FSRS
    scheduling itself lands in Phase 2; here we just seed the deck.
    """
    vocab_ids = [
        r["vocab_id"]
        for r in conn.execute(
            "SELECT vocab_id FROM lesson_vocab WHERE lesson_id = ?", (lesson_id,)
        ).fetchall()
    ]
    created = 0
    for vid in vocab_ids:
        exists = conn.execute(
            """SELECT 1 FROM srs_cards
               WHERE item_type='vocab' AND item_id=? AND card_type='recognition'""",
            (vid,),
        ).fetchone()
        if not exists:
            conn.execute(
                """INSERT INTO srs_cards (item_type, item_id, card_type, state, due)
                   VALUES ('vocab', ?, 'recognition', 'new', datetime('now'))""",
                (vid,),
            )
            created += 1
    return created
