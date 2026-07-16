"""Progress dashboard + activity logging (spec §3.6).

Mastery-based framing (no XP): a vocab item's mastery comes from its FSRS
stability. Activity (reviews / lessons / minutes) is logged per day to drive the
streak and activity chart; tone attempts feed the tone-accuracy trend.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta

# Stability (days) thresholds for mastery bands.
YOUNG_STABILITY = 7.0
MATURE_STABILITY = 21.0


def _today() -> str:
    return date.today().isoformat()


def record_activity(
    conn: sqlite3.Connection,
    *,
    reviews: int = 0,
    lessons: int = 0,
    minutes: float = 0.0,
    day: str | None = None,
) -> None:
    day = day or _today()
    conn.execute(
        """INSERT INTO daily_activity (day, minutes, reviews_done, lessons_done)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(day) DO UPDATE SET
             minutes = minutes + excluded.minutes,
             reviews_done = reviews_done + excluded.reviews_done,
             lessons_done = lessons_done + excluded.lessons_done""",
        (day, minutes, reviews, lessons),
    )
    conn.commit()


def record_tone_attempt(
    conn: sqlite3.Connection, target_text: str, correct: int, total: int, detail: str | None = None
) -> None:
    conn.execute(
        "INSERT INTO tone_attempts (target_text, correct, total, detail) VALUES (?, ?, ?, ?)",
        (target_text, correct, total, detail),
    )
    conn.commit()


def _streak(days_with_activity: set[str]) -> int:
    streak = 0
    d = date.today()
    # Allow the streak to count from today or yesterday (today may be empty yet).
    if d.isoformat() not in days_with_activity and (d - timedelta(days=1)).isoformat() in days_with_activity:
        d = d - timedelta(days=1)
    while d.isoformat() in days_with_activity:
        streak += 1
        d = d - timedelta(days=1)
    return streak


def get_progress(conn: sqlite3.Connection) -> dict:
    # --- Activity (last 14 days) + streak ---
    rows = conn.execute(
        "SELECT day, minutes, reviews_done, lessons_done FROM daily_activity"
    ).fetchall()
    by_day = {r["day"]: r for r in rows}
    active_days = {
        r["day"] for r in rows if (r["reviews_done"] or 0) > 0 or (r["lessons_done"] or 0) > 0
    }
    activity = []
    for i in range(13, -1, -1):
        d = (date.today() - timedelta(days=i)).isoformat()
        r = by_day.get(d)
        activity.append({
            "day": d,
            "reviews": r["reviews_done"] if r else 0,
            "lessons": r["lessons_done"] if r else 0,
            "minutes": round(r["minutes"], 1) if r else 0.0,
        })

    # --- Words known by HSK level, split by mastery band ---
    levels: dict[int, dict[str, int]] = {}
    seen: set[tuple] = set()
    for r in conn.execute(
        """SELECT v.hsk_level AS lvl, c.item_id AS vid, c.stability AS s, c.state AS st
           FROM srs_cards c JOIN vocab v ON v.id = c.item_id
           WHERE c.item_type = 'vocab' AND c.card_type = 'recognition'"""
    ).fetchall():
        lvl = r["lvl"] or 0
        if (lvl, r["vid"]) in seen:
            continue
        seen.add((lvl, r["vid"]))
        band = levels.setdefault(lvl, {"learning": 0, "young": 0, "mature": 0})
        s = r["s"]
        if s is None or r["st"] == "new" or s < YOUNG_STABILITY:
            band["learning"] += 1
        elif s < MATURE_STABILITY:
            band["young"] += 1
        else:
            band["mature"] += 1
    words_by_hsk = [
        {"hsk_level": lvl, **levels[lvl]} for lvl in sorted(levels)
    ]
    total_known = sum(sum(b.values()) for b in levels.values())
    total_mature = sum(b["mature"] for b in levels.values())

    # --- Tone-accuracy trend (recent attempts) ---
    tone_rows = conn.execute(
        "SELECT correct, total, occurred_at FROM tone_attempts ORDER BY occurred_at DESC LIMIT 50"
    ).fetchall()
    tone_total = sum(r["total"] for r in tone_rows)
    tone_correct = sum(r["correct"] for r in tone_rows)
    tone_accuracy = round(tone_correct / tone_total, 3) if tone_total else None
    # Small trend: accuracy per recent attempt (oldest→newest), capped.
    tone_trend = [
        round(r["correct"] / r["total"], 3)
        for r in reversed(tone_rows)
        if r["total"]
    ][-20:]

    # --- SRS retention (recent ratings ≥ Good) ---
    ret = conn.execute(
        "SELECT rating FROM review_log ORDER BY reviewed_at DESC LIMIT 100"
    ).fetchall()
    retention = (
        round(sum(1 for r in ret if r["rating"] >= 3) / len(ret), 3) if ret else None
    )

    # --- Weakest grammar points (from drill error log) ---
    weak = conn.execute(
        """SELECT g.id, g.title, COUNT(*) AS errors
           FROM drill_errors d JOIN grammar g ON g.id = d.grammar_id
           WHERE d.grammar_id IS NOT NULL
           GROUP BY d.grammar_id ORDER BY errors DESC LIMIT 5"""
    ).fetchall()
    weakest_grammar = [{"id": r["id"], "title": r["title"], "errors": r["errors"]} for r in weak]

    return {
        "streak": _streak(active_days),
        "activity": activity,
        "words_by_hsk": words_by_hsk,
        "total_known": total_known,
        "total_mature": total_mature,
        "tone_accuracy": tone_accuracy,
        "tone_trend": tone_trend,
        "retention": retention,
        "weakest_grammar": weakest_grammar,
    }


# Rough time estimates so the minutes/day figure is meaningful without a timer.
def review_minutes(n: int = 1) -> float:
    return 0.2 * n


def lesson_minutes() -> float:
    return 3.0
