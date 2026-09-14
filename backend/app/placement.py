"""Adaptive placement check (spec §3.1).

"A short placement quiz (vocab recognition + a couple of listening clips + a
couple of sentence-building items) run once, used to seed which TOCFL/HSK-
equivalent bands are marked 'known' vs 'to learn.'"

The previous version asked 30 recognition questions over HSK 1–2 and could not
place a learner above HSK 2 — which for someone at TOCFL A2/B1 measures nothing.
The spec is explicit that this should not be "a cold start at HSK1".

So this walks bands instead of sampling one. It starts mid-range, asks a short
round, and steps up or down depending on how it goes, stopping at the boundary
between what the learner knows and what they don't. Eight items per band finds
that boundary in three or four rounds, which is the "short" the spec asks for —
an exhaustive test of 1,250 words would be more accurate and nobody would finish
it.

Each round mixes the three item kinds the spec names: recognition, listening
(audio with no characters shown), and sentence building (reorder the words).

**On what gets seeded.** A band judged "known" does NOT mass-seed mature SRS
cards for every word in it. Claiming Jacob knows 611 HSK 4 words on the strength
of 8 questions would poison the review queue with material he has never seen,
and FSRS would take months to work the error back out. Only items actually
tested get cards. The band verdict is recorded separately, in band_state, as
what it is: an estimate of where to start.
"""

from __future__ import annotations

import json
import random
import sqlite3

from . import levels, srs
from .exercises import _distractor_glosses, _distractor_words, _mc, short_gloss

# Items per band. Enough to be meaningful, few enough that four rounds is quick.
ROUND_SIZE = 8

# Where to begin. Starting at band 1 wastes rounds on a learner who is past it,
# and starting at 4 is demoralising for one who isn't. Band 2 reaches either end
# in two steps.
START_BAND = 2

# Score thresholds for a band.
KNOWN = 0.80     # at or above: the learner has this band, step up
TO_LEARN = 0.50  # below: they don't, step down; between the two is the boundary

STATUS_KNOWN = "known"
STATUS_PARTIAL = "partial"
STATUS_TO_LEARN = "to_learn"

MAX_ROUNDS = len(levels.BANDS)


# ---------------------------------------------------------------------------
# Building a round
# ---------------------------------------------------------------------------
def _band_vocab(conn: sqlite3.Connection, hsk_level: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM vocab WHERE hsk_level = ? ORDER BY RANDOM()", (hsk_level,)
    ).fetchall()
    return [dict(r) for r in rows]


def _band_sentences(conn: sqlite3.Connection, hsk_level: int) -> list[dict]:
    """Drill sentences from live units at this band, for the reordering items.

    Live units only: draft units have no sentences, which is precisely what
    makes them drafts.
    """
    rows = conn.execute(
        """SELECT l.sentences FROM lessons l JOIN units u ON u.id = l.unit_id
           WHERE u.hsk_level = ? AND u.status = 'live'""",
        (hsk_level,),
    ).fetchall()
    out: list[dict] = []
    for r in rows:
        for s in json.loads(r["sentences"] or "[]"):
            tokens = s.get("tokens") or []
            # Two tokens can only be ordered one wrong way; five or more is
            # fiddly on a phone. Three or four is the useful range.
            if 3 <= len(tokens) <= 5:
                out.append(s)
    return out


def build_round(conn: sqlite3.Connection, hsk_level: int, seen: set[str] | None = None) -> dict:
    """One band's worth of questions: recognition, listening, sentence building."""
    seen = seen or set()
    pool = [dict(r) for r in conn.execute("SELECT * FROM vocab").fetchall()]
    candidates = [v for v in _band_vocab(conn, hsk_level) if v["id"] not in seen]
    rng = random.Random(f"placement:{hsk_level}:{len(seen)}")

    sentences = _band_sentences(conn, hsk_level)
    # "A couple of" each, per the spec; the rest recognition.
    n_listening = 2 if len(candidates) >= 4 else 0
    n_sentence = min(2, len(sentences))
    n_recognition = max(0, ROUND_SIZE - n_listening - n_sentence)

    items: list[dict] = []
    for v in candidates[:n_recognition]:
        items.append({
            "kind": "recognition",
            "vocab_id": v["id"],
            "char": v["traditional"],
            "pinyin": v.get("pinyin"),
            "options": _mc(short_gloss(v["gloss"]), _distractor_glosses(pool, v["id"], 3, rng), rng),
        })

    for v in candidates[n_recognition : n_recognition + n_listening]:
        items.append({
            "kind": "listening",
            "vocab_id": v["id"],
            # No char and no pinyin: the point is whether he recognises it by ear.
            "audio_text": v["traditional"],
            "options": _mc(short_gloss(v["gloss"]), _distractor_glosses(pool, v["id"], 3, rng), rng),
        })

    for s in rng.sample(sentences, n_sentence) if n_sentence else []:
        tokens = list(s["tokens"])
        shuffled = tokens[:]
        # Guarantee the shuffle actually moved something.
        while len(tokens) > 1 and shuffled == tokens:
            rng.shuffle(shuffled)
        items.append({
            "kind": "sentence_build",
            "vocab_id": None,
            "tokens": shuffled,
            "answer": tokens,
            "gloss": s.get("gloss"),
            "pinyin": s.get("pinyin"),
        })

    rng.shuffle(items)
    return {
        "band": hsk_level,
        "level": levels.band(hsk_level),
        "items": items,
        "round_size": len(items),
    }


# ---------------------------------------------------------------------------
# Scoring a round and deciding where to go next
# ---------------------------------------------------------------------------
def classify(score: float) -> str:
    if score >= KNOWN:
        return STATUS_KNOWN
    if score < TO_LEARN:
        return STATUS_TO_LEARN
    return STATUS_PARTIAL


def next_band(hsk_level: int, status: str, visited: set[int]) -> int | None:
    """Step up on a pass, down on a fail, stop at the boundary.

    Returns None when the quiz is finished — either the boundary was found, or
    the walk ran off the top or bottom of the scale, or it would revisit a band
    it already answered (which would loop forever at a fluctuating score).
    """
    if status == STATUS_PARTIAL:
        return None  # this band is the boundary: exactly where to start
    step = 1 if status == STATUS_KNOWN else -1
    candidate = hsk_level + step
    if candidate not in levels.BANDS or candidate in visited:
        return None
    return candidate


def record_round(conn: sqlite3.Connection, hsk_level: int, results: list[dict]) -> dict:
    """Score a band, store the verdict, and seed SRS cards for what was tested."""
    gradable = [r for r in results if r.get("vocab_id")]
    total = len(results) or 1
    correct = sum(1 for r in results if r.get("correct"))
    score = correct / total
    status = classify(score)

    conn.execute(
        """INSERT INTO band_state (hsk_level, status, score, sampled, assessed_at)
           VALUES (?, ?, ?, ?, datetime('now'))
           ON CONFLICT(hsk_level) DO UPDATE SET
             status=excluded.status, score=excluded.score,
             sampled=excluded.sampled, assessed_at=excluded.assessed_at""",
        (hsk_level, status, score, len(results)),
    )

    # Only what was actually asked. See the note at the top of this module.
    seeded_known = seeded_new = 0
    for r in gradable:
        if r.get("correct"):
            srs.seed_mature(conn, "vocab", r["vocab_id"], "recognition")
            seeded_known += 1
        else:
            srs.ensure_new_card(conn, "vocab", r["vocab_id"], "recognition")
            seeded_new += 1
    conn.commit()

    return {
        "band": hsk_level,
        "status": status,
        "score": round(score, 3),
        "correct": correct,
        "total": total,
        "seeded_known": seeded_known,
        "seeded_new": seeded_new,
    }


# ---------------------------------------------------------------------------
# Finishing
# ---------------------------------------------------------------------------
def band_states(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM band_state ORDER BY hsk_level").fetchall()
    by_level = {r["hsk_level"]: dict(r) for r in rows}
    out = []
    for level in levels.BANDS:
        state = by_level.get(level)
        out.append({
            **levels.band(level),
            "status": state["status"] if state else None,
            "score": state["score"] if state else None,
            "sampled": state["sampled"] if state else 0,
            "assessed": state is not None,
        })
    return out


def estimated_level(conn: sqlite3.Connection) -> dict | None:
    """The band to start from: the boundary, or one past the highest band known."""
    states = [s for s in band_states(conn) if s["assessed"]]
    if not states:
        return None
    partial = [s for s in states if s["status"] == STATUS_PARTIAL]
    if partial:
        return partial[0]
    known = [s for s in states if s["status"] == STATUS_KNOWN]
    if known:
        highest = max(s["hsk_level"] for s in known)
        return levels.band(min(highest + 1, max(levels.BANDS)))
    return levels.band(min(levels.BANDS))


def finalize(conn: sqlite3.Connection) -> dict:
    conn.execute(
        "UPDATE settings SET placement_done = 1, updated_at = datetime('now') WHERE id = 1"
    )
    conn.commit()
    return summary(conn)


def summary(conn: sqlite3.Connection) -> dict:
    cards = conn.execute(
        "SELECT COUNT(*) AS n FROM srs_cards WHERE state = 'review'"
    ).fetchone()["n"]
    new = conn.execute(
        "SELECT COUNT(*) AS n FROM srs_cards WHERE state = 'new'"
    ).fetchone()["n"]
    return {
        "bands": band_states(conn),
        "start_at": estimated_level(conn),
        "known_cards": cards,
        "new_cards": new,
        "caveat": levels.caveat(),
    }


def reset(conn: sqlite3.Connection) -> None:
    """Clear the placement verdict so the quiz can be retaken.

    Deliberately leaves SRS cards alone: those are review history, and throwing
    them away to redo a placement estimate would cost real progress.
    """
    conn.execute("DELETE FROM band_state")
    conn.execute(
        "UPDATE settings SET placement_done = 0, updated_at = datetime('now') WHERE id = 1"
    )
    conn.commit()
