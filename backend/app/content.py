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
from .zhuyin import to_zhuyin

CONTENT_PATH = REPO_ROOT / "content" / "curriculum.json"
HSK1_PATH = REPO_ROOT / "content" / "hsk1.json"
TOCFL_PATH = REPO_ROOT / "content" / "tocfl_mapping.json"


def _tocfl_by_hsk() -> dict[int, str]:
    """HSK level → aligned TOCFL level. Derived rather than stored per word,
    since it is a function of hsk_level (content/tocfl_mapping.json)."""
    if not TOCFL_PATH.is_file():
        return {}
    data = json.loads(TOCFL_PATH.read_text(encoding="utf-8"))
    return {lv["hsk_level"]: lv["tocfl_level"] for lv in data.get("levels", [])}


TOCFL_BY_HSK = _tocfl_by_hsk()

# Passing score to complete a lesson and unlock the next (spec §3.1).
PASS_THRESHOLD = 0.8


def _upsert_vocab(conn: sqlite3.Connection, v: dict) -> None:
    ex = v.get("example") or {}
    # Zhuyin is derived from pinyin here rather than authored in the content, so
    # every word gets it for free. to_zhuyin returns None when it cannot convert
    # safely; the column stays NULL and the UI falls back to pinyin.
    zhuyin = v.get("zhuyin") or to_zhuyin(v["pinyin"], v["traditional"])
    example_zhuyin = ex.get("zhuyin") or to_zhuyin(ex.get("pinyin"), ex.get("hanzi"))
    conn.execute(
        """INSERT INTO vocab
             (id, traditional, pinyin, gloss, hsk_level, tocfl_level, taiwan_note,
              example_hanzi, example_pinyin, example_gloss, zhuyin, example_zhuyin)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             traditional=excluded.traditional, pinyin=excluded.pinyin,
             gloss=excluded.gloss, hsk_level=excluded.hsk_level,
             tocfl_level=excluded.tocfl_level, taiwan_note=excluded.taiwan_note,
             example_hanzi=excluded.example_hanzi,
             example_pinyin=excluded.example_pinyin,
             example_gloss=excluded.example_gloss,
             zhuyin=excluded.zhuyin,
             example_zhuyin=excluded.example_zhuyin""",
        (v["id"], v["traditional"], v["pinyin"], v["gloss"],
         v.get("hsk_level"),
         v.get("tocfl_level") or TOCFL_BY_HSK.get(v.get("hsk_level")),
         v.get("taiwan_note"),
         ex.get("hanzi"), ex.get("pinyin"), ex.get("gloss"),
         zhuyin, example_zhuyin),
    )


def _with_zhuyin(items: list[dict], hanzi_key: str | None) -> list[dict]:
    """Annotate a list of {hanzi|tokens, pinyin} objects with a derived zhuyin.

    Drill sentences carry `tokens` rather than a joined `hanzi` string, so the
    caller passes None for those and the tokens are joined here. Objects that
    already have a zhuyin, or that cannot be converted, are left as they are.
    """
    out = []
    for item in items:
        item = dict(item)
        if not item.get("zhuyin") and item.get("pinyin"):
            hanzi = item.get(hanzi_key) if hanzi_key else "".join(item.get("tokens", []))
            z = to_zhuyin(item["pinyin"], hanzi)
            if z:
                item["zhuyin"] = z
        out.append(item)
    return out


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
            """INSERT INTO units
                 (id, title, subtitle, hsk_level, tocfl_level, tocfl_band, sort_order)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 title=excluded.title, subtitle=excluded.subtitle,
                 hsk_level=excluded.hsk_level, tocfl_level=excluded.tocfl_level,
                 tocfl_band=excluded.tocfl_band, sort_order=excluded.sort_order""",
            (unit["id"], unit["title"], unit.get("subtitle"),
             unit.get("hsk_level"), unit.get("tocfl_level"), unit.get("tocfl_band"),
             unit.get("sort_order", 0)),
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
                 json.dumps(_with_zhuyin(lesson.get("dialogue", []), "hanzi"),
                            ensure_ascii=False),
                 json.dumps(_with_zhuyin(lesson.get("sentences", []), None),
                            ensure_ascii=False)),
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
                     json.dumps(_with_zhuyin(g.get("examples", []), "hanzi"),
                                ensure_ascii=False),
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


def prune_curriculum(conn: sqlite3.Connection, data: dict) -> dict:
    """Delete curriculum rows absent from `data`, and re-link lesson vocab.

    `load_curriculum` is a pure upsert, so re-importing a rebuilt curriculum
    leaves rows behind: units and lessons that were renamed still exist, and
    because lesson_vocab links are inserted ON CONFLICT DO NOTHING, a word moved
    from one lesson to another keeps its old link forever. Both show up as
    duplicated lessons in the Learn list and double SRS enrolment.

    Call this *before* load_curriculum. It never touches srs_cards or
    lesson_progress — a learner's history outlives a content rebuild — so a card
    can briefly point at a deleted vocab id; review.build_queue joins on vocab
    and simply skips those.
    """
    unit_ids, lesson_ids, vocab_ids = set(), set(), set()
    for unit in data.get("units", []):
        unit_ids.add(unit["id"])
        for lesson in unit.get("lessons", []):
            lesson_ids.add(lesson["id"])
            vocab_ids.update(v["id"] for v in lesson.get("vocab", []))

    # The HSK 1 placement pool lives in its own file and is not part of `data`.
    keep_vocab = set(vocab_ids)
    if HSK1_PATH.is_file():
        pool = json.loads(HSK1_PATH.read_text(encoding="utf-8"))
        keep_vocab.update(v["id"] for v in pool.get("vocab", []))

    def delete_absent(table: str, keep: set[str]) -> int:
        rows = [r["id"] for r in conn.execute(f"SELECT id FROM {table}").fetchall()]
        gone = [r for r in rows if r not in keep]
        for rid in gone:
            conn.execute(f"DELETE FROM {table} WHERE id = ?", (rid,))
        return len(gone)

    removed = {
        "lessons": delete_absent("lessons", lesson_ids),
        "units": delete_absent("units", unit_ids),
        "vocab": delete_absent("vocab", keep_vocab),
    }

    # Rebuild the join rows outright so a moved word lands in its new lesson.
    cur = conn.execute("DELETE FROM lesson_vocab")
    removed["lesson_vocab_links"] = cur.rowcount if cur.rowcount > 0 else 0
    conn.execute("DELETE FROM lesson_grammar")
    conn.commit()
    return removed


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
            "tocfl_level": _opt(u, "tocfl_level"),
            "tocfl_band": _opt(u, "tocfl_band"),
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


def _opt(row: sqlite3.Row, key: str):
    """Read a column that may be absent on an un-migrated row."""
    return row[key] if key in row.keys() else None


def _vocab_dict(v: sqlite3.Row) -> dict:
    return {
        "id": v["id"],
        "traditional": v["traditional"],
        "pinyin": v["pinyin"],
        "gloss": v["gloss"],
        "hsk_level": v["hsk_level"],
        "tocfl_level": _opt(v, "tocfl_level"),
        "taiwan_note": v["taiwan_note"],
        "zhuyin": _opt(v, "zhuyin"),
        "example": {
            "hanzi": v["example_hanzi"],
            "pinyin": v["example_pinyin"],
            "gloss": v["example_gloss"],
            "zhuyin": _opt(v, "example_zhuyin"),
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
