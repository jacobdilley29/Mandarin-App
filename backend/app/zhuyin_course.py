"""The 注音 mini-course: teaching the alphabet the rest of the app prints.

Every vocabulary card, passage and tile in this app can show zhuyin, because
zhuyin is what Taiwan actually uses — children learn it, keyboards use it,
dictionaries print it. None of that helps a learner who cannot read it yet.
This module is the course that fixes that: the 37 symbols, the order they are
recited in, and the sound each one makes.

Three decisions worth knowing before reading the code:

**Audio always plays a Han character, never a symbol.** edge-tts reads Han; ask
it for ㄅ and you get silence or a shrug. So each symbol in content/zhuyin.json
carries a `voice` character holding its conventional teaching sound — ㄅ is
voiced by 波 bō, the syllable Taiwanese children chant. A test transcribes each
of those readings back with our own converter and insists the symbol is in it,
so a typo in the content file fails the suite instead of teaching a wrong sound.

**The content lives outside the curriculum.** A unit of bare bopomofo would be
refused by the scope validator, which requires every character to be one the
learner has already met — quite rightly, and not a rule worth bending for
something that is not curriculum in the first place. content/zhuyin.json sits
beside content/listen.json instead, hand-authored and loaded directly.

**Symbols are ordinary SRS items.** Unlike reading passages, which are
scheduled but quarantined in their own tab, zhuyin joins the main review queue
(srs.QUEUE_ITEM_TYPES), so a symbol that hasn't stuck comes back on its own.
"""

from __future__ import annotations

import functools
import json
import random
import sqlite3
from pathlib import Path

from . import srs
from .config import REPO_ROOT

CONTENT_PATH: Path = REPO_ROOT / "content" / "zhuyin.json"

ITEM_TYPE = "zhuyin"
CARD_TYPE = "zhuyin_sound"

# The course is short and its drills are unambiguous, so a lesson is passed on
# a higher bar than the curriculum's: there is no sentence to half-understand.
PASS_THRESHOLD = 0.8

# Wrong answers per multiple-choice drill.
OPTIONS = 4


@functools.lru_cache(maxsize=1)
def _load() -> dict:
    return json.loads(CONTENT_PATH.read_text(encoding="utf-8"))


def symbols() -> list[dict]:
    """All 41 entries — the 37 symbols plus the four tone marks."""
    return _load()["symbols"]


def lessons() -> list[dict]:
    return _load()["lessons"]


def groups() -> dict[str, str]:
    return _load()["groups"]


def _by_symbol() -> dict[str, dict]:
    return {s["symbol"]: s for s in symbols()}


def _lesson_by_id(lesson_id: str) -> dict | None:
    return next((les for les in lessons() if les["id"] == lesson_id), None)


# ---------------------------------------------------------------------------
# Exercises
# ---------------------------------------------------------------------------
def _rng(seed: str) -> random.Random:
    return random.Random(f"zhuyin:{seed}")


def _mc(correct: str, wrong: list[str], rng: random.Random) -> list[dict]:
    opts = [{"text": correct, "correct": True}] + [
        {"text": w, "correct": False} for w in wrong
    ]
    rng.shuffle(opts)
    return opts


def _lesson_for(symbol: str) -> dict | None:
    return next((les for les in lessons() if symbol in les["symbols"]), None)


def _confusable(target: dict, rng: random.Random, n: int) -> list[str]:
    """Wrong answers that are actually hard to tell from `target`.

    Its own lesson first, then its group, then anything. The lesson is the
    sharpest distinction available and the one being taught: ㄅ against ㄆㄇㄈ
    is the question — they are all made at the lips and differ by a puff of
    air — where ㄅ against ㄍ is no question at all, and ㄅ against ㄤ is not
    even the same kind of thing.
    """
    lesson = _lesson_for(target["symbol"])
    siblings = set(lesson["symbols"]) if lesson else set()

    others = [s for s in symbols() if s["symbol"] != target["symbol"]]
    buckets: list[list[str]] = [
        [s["symbol"] for s in others if s["symbol"] in siblings],
        [s["symbol"] for s in others if s["symbol"] not in siblings
         and s["group"] == target["group"]],
        [s["symbol"] for s in others if s["symbol"] not in siblings
         and s["group"] != target["group"]],
    ]
    out: list[str] = []
    for bucket in buckets:
        rng.shuffle(bucket)
        out.extend(bucket)
        if len(out) >= n:
            break
    return out[:n]


def build_stream(lesson: dict) -> list[dict]:
    """A lesson's cards: meet each symbol, then four ways of being asked about it."""
    by_symbol = _by_symbol()
    in_lesson = [by_symbol[s] for s in lesson["symbols"] if s in by_symbol]

    stream: list[dict] = []

    def add(kind: str, payload: dict, gradable: bool = True) -> None:
        stream.append({
            "id": f"{lesson['id']}-{len(stream)}",
            "kind": kind,
            "gradable": gradable,
            "payload": payload,
        })

    # 1. Meet each symbol: what it looks like, sounds like, and shows up in.
    for s in in_lesson:
        add("zhuyin_intro", {
            "symbol": s["symbol"],
            "pinyin": s["pinyin"],
            "group": s["group"],
            "order": s["order"],
            "note": s["note"],
            "audio_text": s["voice"],
            "voice": s["voice"],
            "voice_pinyin": s["voice_pinyin"],
            "example": s["example"],
        }, gradable=False)

    # 2. Hear it, pick it. The direction that matters most: this is what
    #    reading zhuyin off a page actually requires.
    for s in in_lesson:
        rng = _rng(f"sound:{lesson['id']}:{s['symbol']}")
        add("zhuyin_sound", {
            "symbol": s["symbol"],
            "audio_text": s["voice"],
            "options": _mc(s["symbol"], _confusable(s, rng, OPTIONS - 1), rng),
        })

    # 3. See it, name it in pinyin — the bridge from what he already reads.
    for s in in_lesson:
        rng = _rng(f"symbol:{lesson['id']}:{s['symbol']}")
        wrong = [by_symbol[w]["pinyin"] for w in _confusable(s, rng, OPTIONS - 1)]
        add("zhuyin_symbol", {
            "symbol": s["symbol"],
            "audio_text": s["voice"],
            "options": _mc(s["pinyin"], wrong, rng),
        })

    # 4. A real word, so the symbol is seen doing its job rather than reciting.
    for s in in_lesson:
        rng = _rng(f"word:{lesson['id']}:{s['symbol']}")
        example = s["example"]
        wrong = [by_symbol[w]["example"]["gloss"] for w in _confusable(s, rng, OPTIONS - 1)]
        add("zhuyin_word", {
            "symbol": s["symbol"],
            "traditional": example["traditional"],
            "pinyin": example["pinyin"],
            "audio_text": example["traditional"],
            "options": _mc(example["gloss"], wrong, rng),
        })

    # 5. Put the lesson back in order. The order is half of what there is to
    #    learn — it sorts dictionaries, phone keyboards and class registers —
    #    and no amount of one-symbol-at-a-time drilling teaches it.
    if len(in_lesson) >= 3:
        rng = _rng(f"order:{lesson['id']}")
        answer = [s["symbol"] for s in in_lesson]
        tiles = [
            {"text": s["symbol"], "pinyin": s["pinyin"], "zhuyin": None}
            for s in in_lesson
        ]
        rng.shuffle(tiles)
        add("zhuyin_order", {
            "symbol": answer[0],
            "tiles": tiles,
            "answer": answer,
            "prompt": lesson["title"],
        })

    return stream


# ---------------------------------------------------------------------------
# The course, its progress, and the SRS
# ---------------------------------------------------------------------------
def _progress(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    ids = [les["id"] for les in lessons()]
    marks = ", ".join("?" * len(ids))
    rows = conn.execute(
        f"SELECT * FROM lesson_progress WHERE lesson_id IN ({marks})", ids  # noqa: S608
    ).fetchall()
    return {r["lesson_id"]: r for r in rows}


def course(conn: sqlite3.Connection) -> dict:
    """The lesson list, each with its progress and whether it is open yet.

    Lessons unlock in order, like the curriculum's: the first is always open,
    and each later one opens when the one before it is passed. The recitation
    order is the point, so skipping ahead defeats it.
    """
    done = _progress(conn)
    out: list[dict] = []
    previous_complete = True
    for les in lessons():
        row = done.get(les["id"])
        completed = bool(row and row["completed"])
        out.append({
            "id": les["id"],
            "title": les["title"],
            "subtitle": les["subtitle"],
            "note": les["note"],
            "symbols": les["symbols"],
            "completed": completed,
            "best_score": row["best_score"] if row else None,
            "unlocked": previous_complete,
        })
        previous_complete = completed

    learned = conn.execute(
        "SELECT COUNT(*) AS n FROM srs_cards WHERE item_type = ?", (ITEM_TYPE,)
    ).fetchone()["n"]

    return {
        "lessons": out,
        "groups": groups(),
        "total_symbols": len(symbols()),
        "learned_symbols": learned,
    }


def get_lesson(conn: sqlite3.Connection, lesson_id: str) -> dict | None:
    les = _lesson_by_id(lesson_id)
    if not les:
        return None
    stream = build_stream(les)
    return {
        "id": les["id"],
        "title": les["title"],
        "subtitle": les["subtitle"],
        "note": les["note"],
        "symbols": les["symbols"],
        "gradable_count": sum(1 for e in stream if e["gradable"]),
        "exercises": stream,
    }


def record(conn: sqlite3.Connection, lesson_id: str, results: list[dict]) -> dict:
    """Score an attempt; on a pass, enrol the lesson's symbols in the SRS.

    Progress is kept in `lesson_progress` alongside the curriculum's. That
    table is keyed by id alone with no foreign key, so it takes these ids
    happily — but it also means anything counting rows there has to join
    `lessons`, or it will report 注音 lessons as Mandarin ones.
    """
    les = _lesson_by_id(lesson_id)
    if not les:
        raise KeyError(lesson_id)

    total = len(results)
    correct = sum(1 for r in results if r.get("correct"))
    score = (correct / total) if total else 0.0
    passed = score >= PASS_THRESHOLD

    row = conn.execute(
        "SELECT * FROM lesson_progress WHERE lesson_id = ?", (lesson_id,)
    ).fetchone()
    prev_best = row["best_score"] if row and row["best_score"] is not None else 0.0
    already_done = bool(row and row["completed"])

    conn.execute(
        """INSERT INTO lesson_progress (lesson_id, completed, best_score, unlocked, completed_at)
           VALUES (?, ?, ?, 1, CASE WHEN ? THEN datetime('now') ELSE NULL END)
           ON CONFLICT(lesson_id) DO UPDATE SET
             completed=excluded.completed, best_score=excluded.best_score,
             completed_at=COALESCE(lesson_progress.completed_at, excluded.completed_at)""",
        (lesson_id, int(already_done or passed), max(prev_best, score), passed),
    )

    new_cards = 0
    if passed and not already_done:
        for sym in les["symbols"]:
            # ensure_new_card returns an id either way, so ask first: a symbol
            # already enrolled is not a new card, however it got there.
            existing = conn.execute(
                "SELECT 1 FROM srs_cards WHERE item_type=? AND item_id=? AND card_type=?",
                (ITEM_TYPE, sym, CARD_TYPE),
            ).fetchone()
            srs.ensure_new_card(conn, ITEM_TYPE, sym, CARD_TYPE)
            if not existing:
                new_cards += 1
    conn.commit()

    return {
        "score": score,
        "correct": correct,
        "total": total,
        "passed": passed,
        "completed": already_done or passed,
        "best_score": max(prev_best, score),
        "new_srs_cards": new_cards,
    }


def render_card(card: sqlite3.Row) -> dict | None:
    """One symbol as a review item, for the daily queue.

    Returns None for a card whose symbol is no longer in the content file — it
    is hand-authored and editable, and a stale card must not take the queue
    down with it.
    """
    s = _by_symbol().get(card["item_id"])
    if not s:
        return None
    rng = _rng(f"review:{card['item_id']}:{card['reps']}")
    return {
        "kind": "zhuyin_recall",
        # `char` and `answer` are the queue's shared vocabulary for "the thing
        # being recalled" — filling them in means the reveal panel and the
        # rating strip work unchanged. Without `char` the reveal would fall
        # through to audio_text and proudly show 波 instead of ㄅ.
        "char": s["symbol"],
        "answer": s["symbol"],
        "symbol": s["symbol"],
        "pinyin": s["pinyin"],
        "group": s["group"],
        "note": s["note"],
        "example": s["example"],
        "audio_text": s["voice"],
        "options": _mc(s["symbol"], _confusable(s, rng, OPTIONS - 1), rng),
    }
