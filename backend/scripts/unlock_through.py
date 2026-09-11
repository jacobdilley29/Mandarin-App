#!/usr/bin/env python3
"""Mark the curriculum complete up to a chosen unit and load it into review.

For a learner who is already past the early material: completes every lesson up
to and including `--through`, then seeds the SRS deck with the vocabulary and
grammar those lessons taught. The next unit becomes the one to actually study.

Due dates are **staggered**, which matters more than it looks. `srs.seed_mature`
puts every card at `now + 10 days`, so seeding a few hundred at once lands them
all on one day; `srs.due_cards` then caps the queue at 60 and computes
`remaining = max(0, limit - len(due))`, so with a backlog that big **no new card
ever enters the deck again**. Spreading the dates keeps the daily load near the
learner's `daily_new_limit` and the queue unjammed.

Usage:
    python -m scripts.unlock_through --list
    python -m scripts.unlock_through --through u_health
    python -m scripts.unlock_through --through u_health --spread 21 --dry-run

Idempotent: re-running with the same target changes nothing.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db, srs  # noqa: E402

DEFAULT_SPREAD_DAYS = 21
# Stability is what FSRS uses to pick the next interval. Ramp it across the
# span so older material comes back less often than the material just covered.
MIN_STABILITY = 6.0
MAX_STABILITY = 25.0


def ordered_units(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, title, hsk_level, sort_order FROM units ORDER BY sort_order"
    ).fetchall()


def lessons_through(conn: sqlite3.Connection, unit_id: str) -> tuple[list[str], int]:
    """Lesson ids up to and including `unit_id`, in curriculum order."""
    units = ordered_units(conn)
    cutoff = next((u["sort_order"] for u in units if u["id"] == unit_id), None)
    if cutoff is None:
        raise SystemExit(f"✗ no unit with id {unit_id!r} (try --list)")
    rows = conn.execute(
        """SELECT l.id FROM lessons l JOIN units u ON u.id = l.unit_id
           WHERE u.sort_order <= ?
           ORDER BY u.sort_order, l.sort_order""",
        (cutoff,),
    ).fetchall()
    return [r["id"] for r in rows], cutoff


def items_for(conn: sqlite3.Connection, lesson_ids: list[str]) -> tuple[list[str], list[str]]:
    """The vocab and grammar taught by those lessons, in curriculum order."""
    if not lesson_ids:
        return [], []
    marks = ",".join("?" * len(lesson_ids))
    vocab = [
        r["vocab_id"] for r in conn.execute(
            f"""SELECT DISTINCT lv.vocab_id, u.sort_order, l.sort_order AS ls, lv.sort_order AS vs
                FROM lesson_vocab lv
                JOIN lessons l ON l.id = lv.lesson_id
                JOIN units u ON u.id = l.unit_id
                WHERE lv.lesson_id IN ({marks})
                ORDER BY u.sort_order, ls, vs""",
            lesson_ids,
        ).fetchall()
    ]
    grammar = [
        r["grammar_id"] for r in conn.execute(
            f"""SELECT DISTINCT lg.grammar_id, u.sort_order, l.sort_order AS ls
                FROM lesson_grammar lg
                JOIN lessons l ON l.id = lg.lesson_id
                JOIN units u ON u.id = l.unit_id
                WHERE lg.lesson_id IN ({marks})
                ORDER BY u.sort_order, ls""",
            lesson_ids,
        ).fetchall()
    ]
    return vocab, grammar


def seed_staggered(
    conn: sqlite3.Connection, item_type: str, item_ids: list[str],
    card_type: str, spread_days: int, offset: int = 0,
) -> int:
    """Seed cards in a mature review state, spread across `spread_days`.

    Position in the list drives both the due date and the stability, so the
    earliest material comes back soonest and at the longest interval.
    """
    if not item_ids:
        return 0
    now = srs.now_utc()
    total = len(item_ids)
    seeded = 0
    for i, item_id in enumerate(item_ids):
        frac = i / max(1, total - 1)
        # Earliest-learned material is the most settled: longest stability.
        stability = MAX_STABILITY - frac * (MAX_STABILITY - MIN_STABILITY)
        day = offset + round(frac * max(0, spread_days - 1))
        due = (now + timedelta(days=day)).isoformat()

        existing = conn.execute(
            "SELECT id FROM srs_cards WHERE item_type=? AND item_id=? AND card_type=?",
            (item_type, item_id, card_type),
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE srs_cards SET state='review', stability=?, difficulty=5.0,
                     due=?, last_review=?, step=NULL WHERE id=?""",
                (stability, due, now.isoformat(), existing["id"]),
            )
        else:
            conn.execute(
                """INSERT INTO srs_cards
                     (item_type, item_id, card_type, state, stability, difficulty,
                      due, last_review)
                   VALUES (?, ?, ?, 'review', ?, 5.0, ?, ?)""",
                (item_type, item_id, card_type, stability, due, now.isoformat()),
            )
        seeded += 1
    return seeded


def complete_lessons(conn: sqlite3.Connection, lesson_ids: list[str]) -> int:
    for lid in lesson_ids:
        conn.execute(
            """INSERT INTO lesson_progress
                 (lesson_id, completed, best_score, unlocked, completed_at)
               VALUES (?, 1, NULL, 1, datetime('now'))
               ON CONFLICT(lesson_id) DO UPDATE SET completed = 1, unlocked = 1,
                 completed_at = COALESCE(lesson_progress.completed_at, datetime('now'))""",
            (lid,),
        )
    return len(lesson_ids)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Complete the curriculum up to a unit and seed review.")
    ap.add_argument("--through", help="unit id to complete up to, inclusive")
    ap.add_argument("--list", action="store_true", help="list unit ids and exit")
    ap.add_argument("--spread", type=int, default=DEFAULT_SPREAD_DAYS,
                    help=f"days to spread due dates over (default {DEFAULT_SPREAD_DAYS})")
    ap.add_argument("--dry-run", action="store_true", help="report without writing")
    args = ap.parse_args()

    db.init_db()
    conn = db.connect()
    try:
        if args.list or not args.through:
            for u in ordered_units(conn):
                print(f"  {u['sort_order']:3}  HSK{u['hsk_level']}  {u['id']:16} {u['title']}")
            if not args.through:
                print("\nPass --through <unit id> to complete up to and including that unit.")
            return 0

        lesson_ids, cutoff = lessons_through(conn, args.through)
        vocab, grammar = items_for(conn, lesson_ids)
        units = ordered_units(conn)
        target = next(u for u in units if u["id"] == args.through)
        nxt = next((u for u in units if u["sort_order"] == cutoff + 1), None)

        print(f"Through unit {cutoff}: {target['title']}")
        print(f"  lessons to complete : {len(lesson_ids)}")
        print(f"  vocab into review   : {len(vocab)}")
        print(f"  grammar into review : {len(grammar)}")
        print(f"  due dates spread    : {args.spread} days "
              f"(~{len(vocab) / max(1, args.spread):.0f} vocab/day)")
        if nxt:
            print(f"  next up to study    : {nxt['title']} ({nxt['id']})")

        if args.dry_run:
            print("\n(dry run — nothing written)")
            return 0

        complete_lessons(conn, lesson_ids)
        n_v = seed_staggered(conn, "vocab", vocab, "recognition", args.spread)
        n_g = seed_staggered(conn, "grammar", grammar, "grammar", args.spread)
        # The Review tab shows the first-run placement quiz until this is set,
        # which would hide the deck we just seeded.
        conn.execute(
            "UPDATE settings SET placement_done = 1, updated_at = datetime('now') WHERE id = 1"
        )
        conn.commit()

        print(f"\n✓ completed {len(lesson_ids)} lessons; "
              f"seeded {n_v} vocab + {n_g} grammar cards")
        print("  Open Review to start; the queue will fill in over the spread.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
