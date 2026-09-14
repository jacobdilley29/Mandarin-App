"""Extra practice that isn't the daily review queue (spec §3.6, §3.1).

Two modes:

  needs_practice — the weak spots. §3.6 asks for "a 'needs practice' view
      surfacing weak spots (e.g. items with poor pronunciation-attempt history
      or repeated SRS lapses), separate from the daily review queue", and those
      are precisely the signals used: SRS lapses, drill errors, and tone-attempt
      accuracy.

  known_material — the opposite end. §3.1 asks for "a 'review known material'
      mode that pulls from already-mastered items ... separately from the 'learn
      new' lesson flow, so review never blocks progression into new content".

**Neither touches FSRS scheduling.** Practice never calls srs.apply_review, so a
session cannot move a due date, add a lapse, or change stability. That is the
point: §3.1 wants review to stop getting in the way of progress, and a practice
mode that punished you for using it — by bringing every drilled card forward, or
by counting a fumbled extra rep as a real lapse — would be the same mistake
wearing different clothes. Drilling here is free.

Time spent is still logged, so practice counts toward the streak.

Items are rendered by review._render / review._render_grammar, so the drills are
the ones the learner already knows rather than a second parallel set.
"""

from __future__ import annotations

import random
import sqlite3

from . import content, review, srs

DEFAULT_SIZE = 12

# Tone attempts at or below this are "poor pronunciation-attempt history" (§3.6).
TONE_WEAK_BELOW = 0.7

# A card is "mastered" once FSRS has it holding for this long (days). Matches
# the threshold the progress dashboard already calls mature.
MATURE_STABILITY = 21.0

# Practice renders flashcard drills, so it draws from the same item types the
# review queue does. A reading passage is scheduled like a card but read, not
# drilled: picked up here it would be dropped at render time, quietly making
# every practice set shorter than it claims to be.
_QUEUE = "item_type IN ({})".format(", ".join("?" * len(srs.QUEUE_ITEM_TYPES)))


def _rows_to_items(
    conn: sqlite3.Connection, rows: list[sqlite3.Row], reasons: dict[int, str] | None = None
) -> list[dict]:
    """Render SRS cards into drill items, exactly as the review queue does."""
    pool = content.all_vocab(conn)
    patterns = [r["pattern"] for r in conn.execute("SELECT pattern FROM grammar")]
    reasons = reasons or {}

    items: list[dict] = []
    for card in rows:
        base = {
            "card_id": card["id"],
            "item_id": card["item_id"],
            "item_type": card["item_type"],
            "reps": card["reps"],
            "state": card["state"],
            "why": reasons.get(card["id"]),
        }
        if card["item_type"] == "vocab":
            v = review._vocab_row(conn, card["item_id"])
            if not v:
                continue
            items.append({**base, **review._render(card, v, pool, review._choose_kind(card, v))})
        elif card["item_type"] == "grammar":
            g = review._grammar_row(conn, card["item_id"])
            if not g:
                continue
            rendered = review._render_grammar_rotating(card, g, patterns)
            if rendered:
                items.append({**base, **rendered})
    return items


# ---------------------------------------------------------------------------
# Needs practice (§3.6)
# ---------------------------------------------------------------------------
def weak_items(conn: sqlite3.Connection, limit: int = DEFAULT_SIZE) -> list[dict]:
    """Cards ranked by how much trouble they have actually caused.

    Three independent signals, summed into one score so an item that is bad in
    several ways outranks one that is merely bad in one:

      lapses       — FSRS forgot-count, the strongest single signal
      drill errors — wrong answers in lessons, per vocab/grammar item
      tone trouble — attempts on this word scoring below TONE_WEAK_BELOW
    """
    scores: dict[int, float] = {}
    reasons: dict[int, list[str]] = {}

    def add(card_id: int, points: float, why: str) -> None:
        scores[card_id] = scores.get(card_id, 0.0) + points
        reasons.setdefault(card_id, []).append(why)

    for r in conn.execute(
        f"""SELECT id, lapses FROM srs_cards
            WHERE lapses > 0 AND {_QUEUE}
            ORDER BY lapses DESC LIMIT 200""",  # noqa: S608 — filter is a literal
        srs.QUEUE_ITEM_TYPES,
    ):
        add(r["id"], 2.0 * r["lapses"], f"forgotten {r['lapses']}x")

    for r in conn.execute(
        """SELECT c.id, COUNT(*) AS n FROM drill_errors d
           JOIN srs_cards c
             ON (c.item_type = 'vocab' AND c.item_id = d.vocab_id)
             OR (c.item_type = 'grammar' AND c.item_id = d.grammar_id)
           GROUP BY c.id ORDER BY n DESC LIMIT 200"""
    ):
        add(r["id"], 1.0 * r["n"], f"{r['n']} drill error{'s' if r['n'] > 1 else ''}")

    for r in conn.execute(
        """SELECT c.id, SUM(t.correct) AS ok, SUM(t.total) AS total
           FROM tone_attempts t
           JOIN vocab v ON v.traditional = t.target_text
           JOIN srs_cards c ON c.item_type = 'vocab' AND c.item_id = v.id
           GROUP BY c.id HAVING total > 0"""
    ):
        accuracy = r["ok"] / r["total"]
        if accuracy <= TONE_WEAK_BELOW:
            add(r["id"], 1.5 * (1 - accuracy), f"tones {round(accuracy * 100)}%")

    if not scores:
        return []

    ranked = sorted(scores, key=lambda cid: scores[cid], reverse=True)[:limit]
    placeholders = ",".join("?" * len(ranked))
    rows = conn.execute(
        f"SELECT * FROM srs_cards WHERE id IN ({placeholders})", ranked  # noqa: S608
    ).fetchall()
    # Preserve the ranking the query above lost.
    by_id = {r["id"]: r for r in rows}
    ordered = [by_id[cid] for cid in ranked if cid in by_id]

    return _rows_to_items(conn, ordered, {cid: ", ".join(reasons[cid]) for cid in ranked})


def needs_practice(conn: sqlite3.Connection, limit: int = DEFAULT_SIZE) -> dict:
    items = weak_items(conn, limit)
    return {
        "mode": "needs_practice",
        "items": items,
        "count": len(items),
        # Said plainly so the screen can explain itself when there's nothing to do.
        "empty_reason": None if items else "Nothing is going badly yet — come back after some reviews.",
    }


# ---------------------------------------------------------------------------
# Known material (§3.1)
# ---------------------------------------------------------------------------
def known_material(conn: sqlite3.Connection, limit: int = DEFAULT_SIZE) -> dict:
    """A sample of what he has already mastered, for confidence-building review.

    Random rather than ranked: the point is to revisit solid ground, and always
    serving the same dozen words would defeat it.
    """
    rows = conn.execute(
        f"""SELECT * FROM srs_cards
            WHERE state = 'review' AND COALESCE(stability, 0) >= ? AND {_QUEUE}
            ORDER BY RANDOM() LIMIT ?""",  # noqa: S608 — filter is a literal
        (MATURE_STABILITY, *srs.QUEUE_ITEM_TYPES, limit),
    ).fetchall()

    items = _rows_to_items(conn, rows)
    return {
        "mode": "known_material",
        "items": items,
        "count": len(items),
        "empty_reason": None if items else "Nothing is mastered yet — keep reviewing and this fills up.",
    }


# ---------------------------------------------------------------------------
# Finishing a session
# ---------------------------------------------------------------------------
def record_session(conn: sqlite3.Connection, answered: int, correct: int) -> dict:
    """Log the practice for the streak — and change nothing about scheduling.

    Deliberately does not call srs.apply_review. See the module docstring.
    """
    from . import progress

    progress.record_activity(conn, reviews=0, minutes=progress.review_minutes(answered))
    conn.commit()
    return {
        "answered": answered,
        "correct": correct,
        "srs_unchanged": True,
    }
