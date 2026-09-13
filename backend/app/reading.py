"""Graded reading, on its own schedule (spec §3.2, §3.6).

Every lesson carries a short passage written to exactly its own level — 60-120
characters of connected prose, held to the same character scope as the rest of
the lesson (see app/validation.py). The drills teach words one at a time; the
passage is where they come back as a paragraph, which is a different skill and
the one that eventually turns into reading Chinese.

**Passages are FSRS-scheduled, like everything else.** Reading a passage once
and never again is how it becomes a text you half-remember rather than a text
you can read. So each one is a card of its own — `item_type='passage'`,
`item_id` the lesson id — rated Again/Hard/Good/Easy on the same four buttons,
and a passage that came out hard resurfaces before one that came out easy. No
new engine: app/srs.py already schedules by (item_type, item_id).

Two rules it inherits deliberately:

  * **A passage unlocks with its lesson, not before.** The prose is built from
    what that lesson taught; served earlier it is exactly the out-of-scope
    reading the whole curriculum pipeline exists to prevent.
  * **Reading never disturbs the vocabulary deck.** Rating a passage moves that
    passage's card and nothing else — the same rule app/practice.py keeps, for
    the same reason: an extra reading session should never cost the learner a
    pile of vocabulary reviews the next morning.
"""

from __future__ import annotations

import json
import sqlite3

from . import levels as _levels, srs

ITEM_TYPE = "passage"
CARD_TYPE = "reading"


def _passage_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Every passage in live units, in curriculum order.

    Draft units are excluded here for the same reason they are excluded from the
    unlock chain: their content has not passed the scope check, and an
    unvalidated passage is precisely the thing this module must not serve.
    """
    return conn.execute(
        """SELECT l.id AS lesson_id, l.title AS lesson_title, l.passage,
                  u.id AS unit_id, u.title AS unit_title, u.hsk_level
           FROM lessons l JOIN units u ON u.id = l.unit_id
           WHERE u.status = 'live' AND l.passage IS NOT NULL
           ORDER BY u.sort_order, l.sort_order"""
    ).fetchall()


def _parse(row: sqlite3.Row) -> dict | None:
    try:
        passage = json.loads(row["passage"] or "null")
    except (TypeError, ValueError):
        return None
    if not passage or not passage.get("hanzi"):
        return None
    return passage


def _cards(conn: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    return {
        r["item_id"]: r
        for r in conn.execute(
            "SELECT * FROM srs_cards WHERE item_type = ? AND card_type = ?",
            (ITEM_TYPE, CARD_TYPE),
        )
    }


def _completed(conn: sqlite3.Connection) -> set[str]:
    return {
        r["lesson_id"]
        for r in conn.execute("SELECT lesson_id FROM lesson_progress WHERE completed = 1")
    }


def library(conn: sqlite3.Connection) -> dict:
    """The Reading tab: what can be read, what is due, what is still locked."""
    completed = _completed(conn)
    cards = _cards(conn)
    now = srs.now_utc().isoformat()

    items: list[dict] = []
    for row in _passage_rows(conn):
        passage = _parse(row)
        if not passage:
            continue
        lesson_id = row["lesson_id"]
        card = cards.get(lesson_id)
        due = bool(card and card["state"] != "new" and (card["due"] or "") <= now)
        items.append(
            {
                "lesson_id": lesson_id,
                "lesson_title": row["lesson_title"],
                "unit_id": row["unit_id"],
                "unit_title": row["unit_title"],
                "hsk_level": row["hsk_level"],
                # The same TOCFL-first badge the Learn map shows, so a passage
                # is labelled by the level the learner has been told they are at.
                "level": _levels.band(row["hsk_level"]),
                "title": passage.get("title") or row["lesson_title"],
                "chars": len(passage["hanzi"]),
                "unlocked": lesson_id in completed,
                "read": bool(card),
                "due": due,
                "due_at": card["due"] if card else None,
                "reps": card["reps"] if card else 0,
            }
        )

    unlocked = [i for i in items if i["unlocked"]]
    return {
        "passages": items,
        "total": len(items),
        "unlocked": len(unlocked),
        "due": sum(1 for i in unlocked if i["due"]),
        "unread": sum(1 for i in unlocked if not i["read"]),
    }


def get_passage(conn: sqlite3.Connection, lesson_id: str) -> dict | None:
    """One passage to read, with the words its lesson taught.

    The vocabulary travels with it so the reader can check a word against what
    the lesson actually said, rather than against a dictionary that may disagree
    on the Taiwan reading.
    """
    row = conn.execute(
        """SELECT l.id AS lesson_id, l.title AS lesson_title, l.passage,
                  u.id AS unit_id, u.title AS unit_title, u.hsk_level, u.status
           FROM lessons l JOIN units u ON u.id = l.unit_id
           WHERE l.id = ?""",
        (lesson_id,),
    ).fetchone()
    if not row or row["status"] != "live":
        return None
    passage = _parse(row)
    if not passage:
        return None

    vocab = [
        {
            "id": v["id"],
            "traditional": v["traditional"],
            "pinyin": v["pinyin"],
            "zhuyin": v["zhuyin"],
            "gloss": v["gloss"],
        }
        for v in conn.execute(
            """SELECT v.* FROM vocab v
               JOIN lesson_vocab lv ON lv.vocab_id = v.id
               WHERE lv.lesson_id = ? ORDER BY lv.sort_order""",
            (lesson_id,),
        )
    ]

    card = _cards(conn).get(lesson_id)
    return {
        "lesson_id": lesson_id,
        "lesson_title": row["lesson_title"],
        "unit_id": row["unit_id"],
        "unit_title": row["unit_title"],
        "hsk_level": row["hsk_level"],
        "level": _levels.band(row["hsk_level"]),
        "title": passage.get("title") or row["lesson_title"],
        "hanzi": passage["hanzi"],
        "gloss": passage.get("gloss") or "",
        "vocab": vocab,
        "unlocked": lesson_id in _completed(conn),
        "card_id": card["id"] if card else None,
        "reps": card["reps"] if card else 0,
        "due_at": card["due"] if card else None,
    }


def due(conn: sqlite3.Connection, limit: int = 10) -> list[dict]:
    """Passages FSRS says it is time to reread, soonest first."""
    now = srs.now_utc().isoformat()
    order = {
        r["item_id"]: i
        for i, r in enumerate(
            conn.execute(
                """SELECT item_id FROM srs_cards
                   WHERE item_type = ? AND card_type = ? AND state != 'new' AND due <= ?
                   ORDER BY due ASC LIMIT ?""",
                (ITEM_TYPE, CARD_TYPE, now, limit),
            )
        )
    }
    if not order:
        return []
    out = [p for p in library(conn)["passages"] if p["lesson_id"] in order]
    return sorted(out, key=lambda p: order[p["lesson_id"]])


def record_read(conn: sqlite3.Connection, lesson_id: str, rating: int) -> dict:
    """Rate a passage after reading it, and reschedule that passage alone.

    Raises KeyError when the lesson has no readable passage, and PermissionError
    when its lesson has not been completed yet.
    """
    if rating not in (1, 2, 3, 4):
        raise ValueError("rating must be 1..4")
    passage = get_passage(conn, lesson_id)
    if not passage:
        raise KeyError(lesson_id)
    if not passage["unlocked"]:
        raise PermissionError(lesson_id)

    card_id = srs.ensure_new_card(conn, ITEM_TYPE, lesson_id, CARD_TYPE)
    result = srs.apply_review(conn, card_id, rating)
    return {**result, "lesson_id": lesson_id}
