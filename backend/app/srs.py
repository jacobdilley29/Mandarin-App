"""Spaced-repetition scheduling with FSRS (spec §3.2).

Thin wrapper over py-fsrs (v5): translates between our `srs_cards` rows and
`fsrs.Card`, applies a rating, and persists the updated schedule. Also seeds
"mature" cards for items the learner already knows (placement check).

py-fsrs uses timezone-aware UTC datetimes; we store them as ISO-8601 strings.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

from fsrs import Card, Rating, Scheduler, State

_scheduler = Scheduler()

_STATE_TO_TEXT = {
    State.Learning: "learning",
    State.Review: "review",
    State.Relearning: "relearning",
}
_TEXT_TO_STATE = {v: k for k, v in _STATE_TO_TEXT.items()}

# Seed values for a card the learner already knows (placement pass). ~10-day
# stability puts the first real review comfortably in the future.
_MATURE_STABILITY = 10.0
_MATURE_DIFFICULTY = 5.0


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse(dt: str | None) -> datetime | None:
    if not dt:
        return None
    d = datetime.fromisoformat(dt)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def row_to_card(row: sqlite3.Row) -> Card:
    """Reconstruct an fsrs.Card from a stored row (or a fresh one if new)."""
    if row["state"] == "new" or row["stability"] is None:
        return Card()  # unreviewed: fresh Learning card
    return Card(
        state=_TEXT_TO_STATE.get(row["state"], State.Learning),
        step=row["step"],
        stability=row["stability"],
        difficulty=row["difficulty"],
        due=_parse(row["due"]),
        last_review=_parse(row["last_review"]),
    )


def _write_card(conn: sqlite3.Connection, card_id: int, card: Card, rating: int) -> None:
    conn.execute(
        """UPDATE srs_cards SET
             stability=?, difficulty=?, due=?, last_review=?, step=?, state=?,
             reps = reps + 1,
             lapses = lapses + ?
           WHERE id = ?""",
        (
            card.stability,
            card.difficulty,
            card.due.isoformat() if card.due else None,
            card.last_review.isoformat() if card.last_review else None,
            card.step,
            _STATE_TO_TEXT.get(card.state, "learning"),
            1 if rating == int(Rating.Again) else 0,
            card_id,
        ),
    )


def apply_review(
    conn: sqlite3.Connection, card_id: int, rating: int, elapsed_ms: int | None = None
) -> dict:
    """Apply a rating to a card, persist the new schedule, and log the review."""
    row = conn.execute("SELECT * FROM srs_cards WHERE id = ?", (card_id,)).fetchone()
    if row is None:
        raise KeyError("card not found")
    if rating not in (1, 2, 3, 4):
        raise ValueError("rating must be 1..4")

    card = row_to_card(row)
    updated, _log = _scheduler.review_card(card, Rating(rating), review_datetime=now_utc())
    _write_card(conn, card_id, updated, rating)
    conn.execute(
        "INSERT INTO review_log (card_id, rating, elapsed_ms) VALUES (?, ?, ?)",
        (card_id, rating, elapsed_ms),
    )
    conn.commit()
    return {
        "card_id": card_id,
        "state": _STATE_TO_TEXT.get(updated.state, "learning"),
        "due": updated.due.isoformat() if updated.due else None,
        "stability": updated.stability,
    }


def seed_mature(
    conn: sqlite3.Connection, item_type: str, item_id: str, card_type: str = "recognition"
) -> int:
    """Create/refresh a card in a mature Review state (placement: known item)."""
    now = now_utc()
    due = (now + timedelta(days=_MATURE_STABILITY)).isoformat()
    existing = conn.execute(
        "SELECT id FROM srs_cards WHERE item_type=? AND item_id=? AND card_type=?",
        (item_type, item_id, card_type),
    ).fetchone()
    if existing:
        conn.execute(
            """UPDATE srs_cards SET state='review', stability=?, difficulty=?,
                 due=?, last_review=?, step=NULL WHERE id=?""",
            (_MATURE_STABILITY, _MATURE_DIFFICULTY, due, now.isoformat(), existing["id"]),
        )
        return existing["id"]
    cur = conn.execute(
        """INSERT INTO srs_cards
             (item_type, item_id, card_type, state, stability, difficulty, due, last_review)
           VALUES (?, ?, ?, 'review', ?, ?, ?, ?)""",
        (item_type, item_id, card_type, _MATURE_STABILITY, _MATURE_DIFFICULTY, due, now.isoformat()),
    )
    return int(cur.lastrowid)


def ensure_new_card(
    conn: sqlite3.Connection, item_type: str, item_id: str, card_type: str = "recognition"
) -> int:
    """Create a brand-new (unreviewed) card if one doesn't already exist."""
    existing = conn.execute(
        "SELECT id FROM srs_cards WHERE item_type=? AND item_id=? AND card_type=?",
        (item_type, item_id, card_type),
    ).fetchone()
    if existing:
        return existing["id"]
    cur = conn.execute(
        """INSERT INTO srs_cards (item_type, item_id, card_type, state, due)
           VALUES (?, ?, ?, 'new', ?)""",
        (item_type, item_id, card_type, now_utc().isoformat()),
    )
    return int(cur.lastrowid)


def due_cards(conn: sqlite3.Connection, new_limit: int, limit: int = 60) -> list[sqlite3.Row]:
    """Today's queue: due reviews first, then up to `new_limit` new cards."""
    now = now_utc().isoformat()
    due = conn.execute(
        """SELECT * FROM srs_cards
           WHERE state != 'new' AND due <= ?
           ORDER BY due ASC LIMIT ?""",
        (now, limit),
    ).fetchall()
    remaining = max(0, limit - len(due))
    new = conn.execute(
        """SELECT * FROM srs_cards
           WHERE state = 'new'
           ORDER BY created_at ASC LIMIT ?""",
        (min(new_limit, remaining),),
    ).fetchall()
    return list(due) + list(new)


def counts(conn: sqlite3.Connection) -> dict:
    """Summary counts for the dashboard / Review landing."""
    now = now_utc().isoformat()
    due = conn.execute(
        "SELECT COUNT(*) AS n FROM srs_cards WHERE state != 'new' AND due <= ?", (now,)
    ).fetchone()["n"]
    new = conn.execute("SELECT COUNT(*) AS n FROM srs_cards WHERE state = 'new'").fetchone()["n"]
    total = conn.execute("SELECT COUNT(*) AS n FROM srs_cards").fetchone()["n"]
    mature = conn.execute(
        "SELECT COUNT(*) AS n FROM srs_cards WHERE stability >= 21"
    ).fetchone()["n"]
    return {"due": due, "new": new, "total": total, "mature": mature}
