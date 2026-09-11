"""Build review-queue items and run the placement check (spec §3.2).

A single SRS card schedules one vocab item; its *presentation* rotates across
review kinds (recognition / recall / audio→meaning / cloze) so the learner sees
the word from several angles. Rating (Again/Hard/Good/Easy) drives FSRS.
"""

from __future__ import annotations

import random
import sqlite3

from . import content, srs
from .exercises import _distractor_glosses, _distractor_words, _mc

# Review render kinds in rotation. cloze only applies when the item has an
# example sentence containing the word.
_ROTATION = ["recognition", "audio_meaning", "recall", "cloze"]


def _vocab_row(conn: sqlite3.Connection, vocab_id: str) -> dict | None:
    r = conn.execute("SELECT * FROM vocab WHERE id = ?", (vocab_id,)).fetchone()
    return dict(r) if r else None


def _pool(conn: sqlite3.Connection) -> list[dict]:
    return content.all_vocab(conn)


def _render(card: sqlite3.Row, v: dict, pool: list[dict], kind: str) -> dict:
    rng = random.Random(f"{card['id']}:{card['reps']}:{kind}")
    trad = v["traditional"]
    gloss = v["gloss"]

    if kind == "recall":
        return {
            "kind": "recall",
            "prompt_gloss": gloss,
            "pinyin": v.get("pinyin"),
            "answer": trad,
            "options": _mc(trad, _distractor_words(pool, trad, 3, rng), rng),
        }
    if kind == "audio_meaning":
        return {
            "kind": "audio_meaning",
            "audio_text": trad,
            "pinyin": v.get("pinyin"),
            "answer": gloss,
            "options": _mc(gloss, _distractor_glosses(pool, v["id"], 3, rng), rng),
        }
    if kind == "cloze" and v.get("example_hanzi") and trad in v["example_hanzi"]:
        masked = v["example_hanzi"].replace(trad, "＿＿", 1)
        return {
            "kind": "cloze",
            "masked": masked,
            "audio_text": v["example_hanzi"],
            "gloss": v.get("example_gloss"),
            "answer": trad,
            "options": _mc(trad, _distractor_words(pool, trad, 3, rng), rng),
        }
    # Default: recognition (char → meaning).
    return {
        "kind": "recognition",
        "char": trad,
        "audio_text": trad,
        "pinyin": v.get("pinyin"),
        "answer": gloss,
        "options": _mc(gloss, _distractor_glosses(pool, v["id"], 3, rng), rng),
    }


def _choose_kind(card: sqlite3.Row, v: dict) -> str:
    kind = _ROTATION[card["reps"] % len(_ROTATION)]
    if kind == "cloze" and not (v.get("example_hanzi") and v["traditional"] in v["example_hanzi"]):
        return "recognition"
    return kind


def build_queue(conn: sqlite3.Connection, new_limit: int) -> list[dict]:
    pool = _pool(conn)
    cards = srs.due_cards(conn, new_limit)
    items: list[dict] = []
    for card in cards:
        if card["item_type"] != "vocab":
            continue
        v = _vocab_row(conn, card["item_id"])
        if not v:
            continue
        kind = _choose_kind(card, v)
        items.append({
            "card_id": card["id"],
            "item_id": card["item_id"],
            "reps": card["reps"],
            "state": card["state"],
            **_render(card, v, pool, kind),
        })
    return items


# ---------------------------------------------------------------------------
# Placement check (first run)
# ---------------------------------------------------------------------------
def placement_items(conn: sqlite3.Connection, n: int = 30) -> list[dict]:
    """A quick recognition quiz over HSK 1–2 foundation vocab."""
    pool = _pool(conn)
    rows = conn.execute(
        """SELECT * FROM vocab
           WHERE hsk_level IN (1, 2)
           ORDER BY hsk_level, RANDOM() LIMIT ?""",
        (n,),
    ).fetchall()
    items = []
    for r in rows:
        v = dict(r)
        rng = random.Random(v["id"])
        items.append({
            "vocab_id": v["id"],
            "char": v["traditional"],
            "pinyin": v["pinyin"],
            "options": _mc(v["gloss"], _distractor_glosses(pool, v["id"], 3, rng), rng),
        })
    return items


def seed_placement(conn: sqlite3.Connection, results: list[dict]) -> dict:
    """Correct → seed a mature card; miss → new card. Marks placement done."""
    seeded_mature = seeded_new = 0
    for r in results:
        vocab_id = r.get("vocab_id")
        if not vocab_id:
            continue
        if r.get("correct"):
            srs.seed_mature(conn, "vocab", vocab_id, "recognition")
            seeded_mature += 1
        else:
            srs.ensure_new_card(conn, "vocab", vocab_id, "recognition")
            seeded_new += 1
    conn.execute(
        "UPDATE settings SET placement_done = 1, updated_at = datetime('now') WHERE id = 1"
    )
    conn.commit()
    return {"seeded_mature": seeded_mature, "seeded_new": seeded_new}
