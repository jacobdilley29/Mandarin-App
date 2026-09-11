"""Build review-queue items and run the placement check (spec §3.2).

A single SRS card schedules one vocab item; its *presentation* rotates across
review kinds (recognition / recall / audio→meaning / cloze) so the learner sees
the word from several angles. Rating (Again/Hard/Good/Easy) drives FSRS.
"""

from __future__ import annotations

import json
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


def _grammar_row(conn: sqlite3.Connection, grammar_id: str) -> dict | None:
    r = conn.execute("SELECT * FROM grammar WHERE id = ?", (grammar_id,)).fetchone()
    return dict(r) if r else None


def _render_grammar(
    card: sqlite3.Row, g: dict, others: list[dict]
) -> dict | None:
    """Show one of the point's examples and ask which pattern it demonstrates.

    Recognising the pattern behind a sentence is the thing worth recalling; the
    multiple-choice shape matches every other card so the rating flow is
    unchanged.
    """
    examples = json.loads(g.get("examples") or "[]")
    if not examples:
        return None
    rng = random.Random(f"{card['id']}:{card['reps']}:grammar")
    ex = examples[rng.randrange(len(examples))]

    distractors = [o["pattern"] for o in others if o["id"] != g["id"] and o.get("pattern")]
    rng.shuffle(distractors)
    seen = {g["pattern"]}
    picked = []
    for d in distractors:
        if d not in seen:
            seen.add(d)
            picked.append(d)
        if len(picked) == 3:
            break

    return {
        "kind": "grammar",
        "prompt_hanzi": ex.get("hanzi"),
        "gloss": ex.get("gloss"),
        "pinyin": ex.get("pinyin"),
        "zhuyin": ex.get("zhuyin"),
        "audio_text": ex.get("hanzi"),
        "title": g["title"],
        "explanation": g["explanation"],
        "answer": g["pattern"],
        "options": _mc(g["pattern"], picked, rng),
    }


def _render(card: sqlite3.Row, v: dict, pool: list[dict], kind: str) -> dict:
    rng = random.Random(f"{card['id']}:{card['reps']}:{kind}")
    trad = v["traditional"]
    gloss = v["gloss"]

    if kind == "recall":
        return {
            "kind": "recall",
            "prompt_gloss": gloss,
            "pinyin": v.get("pinyin"),
            "zhuyin": v.get("zhuyin"),
            "answer": trad,
            "options": _mc(trad, _distractor_words(pool, trad, 3, rng), rng),
        }
    if kind == "audio_meaning":
        return {
            "kind": "audio_meaning",
            "audio_text": trad,
            "pinyin": v.get("pinyin"),
            "zhuyin": v.get("zhuyin"),
            "answer": gloss,
            "options": _mc(gloss, _distractor_glosses(pool, v["id"], 3, rng), rng),
        }
    if kind == "cloze" and v.get("example_hanzi") and trad in v["example_hanzi"]:
        masked = v["example_hanzi"].replace(trad, "＿＿", 1)
        return {
            "kind": "cloze",
            "masked": masked,
            "audio_text": v["example_hanzi"],
            "zhuyin": v.get("example_zhuyin"),
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
        "zhuyin": v.get("zhuyin"),
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
    grammar_pool: list[dict] | None = None
    for card in cards:
        if card["item_type"] == "grammar":
            g = _grammar_row(conn, card["item_id"])
            if not g:
                continue
            if grammar_pool is None:
                grammar_pool = [
                    dict(r) for r in conn.execute("SELECT * FROM grammar").fetchall()
                ]
            rendered = _render_grammar(card, g, grammar_pool)
            if rendered is None:
                continue
            items.append({
                "card_id": card["id"],
                "item_id": card["item_id"],
                "reps": card["reps"],
                "state": card["state"],
                **rendered,
            })
            continue
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
PLACEMENT_LEVELS = (1, 2, 3, 4)


def placement_items(conn: sqlite3.Connection, n: int = 32) -> list[dict]:
    """A quick recognition quiz, sampled evenly across HSK 1–4.

    The sample must be stratified. A single `ORDER BY hsk_level, RANDOM() LIMIT n`
    sorts by level *first*, so HSK 1 is exhausted before a single HSK 2 word can
    appear — the quiz was 100% HSK 1 regardless of what the learner knew. Drawing
    a fixed quota per level is what lets `seed_placement` tell which levels the
    learner has already cleared.
    """
    pool = _pool(conn)
    per_level = max(1, n // len(PLACEMENT_LEVELS))
    rows: list[sqlite3.Row] = []
    for level in PLACEMENT_LEVELS:
        rows.extend(conn.execute(
            "SELECT * FROM vocab WHERE hsk_level = ? ORDER BY RANDOM() LIMIT ?",
            (level, per_level),
        ).fetchall())

    items = []
    for r in rows:
        v = dict(r)
        rng = random.Random(v["id"])
        items.append({
            "vocab_id": v["id"],
            "char": v["traditional"],
            "pinyin": v["pinyin"],
            "zhuyin": v.get("zhuyin"),
            "hsk_level": v["hsk_level"],
            "options": _mc(v["gloss"], _distractor_glosses(pool, v["id"], 3, rng), rng),
        })
    return items


# A level counts as already known when the learner gets at least this share of
# its placement items right. Deliberately strict: clearing a level skips every
# lesson in it, so a false positive costs more than a false negative.
LEVEL_PASS_RATIO = 0.8


def seed_placement(conn: sqlite3.Connection, results: list[dict]) -> dict:
    """Correct → seed a mature card; miss → new card. Marks placement done.

    Also completes the lessons of any HSK level the learner clearly already
    knows. Without this, placement only ever seeded SRS cards, so a learner who
    aced HSK 1 still had to work through every HSK 1 lesson to unlock HSK 2 —
    the unlock chain in content.get_curriculum is strictly linear and nothing
    else opens it. It additionally repairs a trap: a correct answer seeds a
    *mature* card for a word whose lesson has not run, and `_enrol_vocab_srs`
    skips words that already have a card, so the lesson would silently never
    introduce it. Completing the level keeps the two consistent.
    """
    seeded_mature = seeded_new = 0
    by_level: dict[int, list[bool]] = {}

    for r in results:
        vocab_id = r.get("vocab_id")
        if not vocab_id:
            continue
        correct = bool(r.get("correct"))
        if correct:
            srs.seed_mature(conn, "vocab", vocab_id, "recognition")
            seeded_mature += 1
        else:
            srs.ensure_new_card(conn, "vocab", vocab_id, "recognition")
            seeded_new += 1

        level = r.get("hsk_level")
        if level is None:
            row = conn.execute(
                "SELECT hsk_level FROM vocab WHERE id = ?", (vocab_id,)
            ).fetchone()
            level = row["hsk_level"] if row else None
        if level is not None:
            by_level.setdefault(int(level), []).append(correct)

    cleared = _complete_cleared_levels(conn, by_level)

    conn.execute(
        "UPDATE settings SET placement_done = 1, updated_at = datetime('now') WHERE id = 1"
    )
    conn.commit()
    return {
        "seeded_mature": seeded_mature,
        "seeded_new": seeded_new,
        "levels_cleared": cleared,
    }


def _complete_cleared_levels(
    conn: sqlite3.Connection, by_level: dict[int, list[bool]]
) -> list[int]:
    """Mark every lesson of a cleared level complete, so the next level unlocks.

    Levels are cleared from the bottom up and stop at the first miss: clearing
    HSK 3 while HSK 1 is shaky would strand the learner behind a locked lesson
    they cannot reach.
    """
    cleared: list[int] = []
    for level in sorted(by_level):
        answers = by_level[level]
        if not answers or sum(answers) / len(answers) < LEVEL_PASS_RATIO:
            break
        cleared.append(level)

    if not cleared:
        return []

    rows = conn.execute(
        """SELECT l.id FROM lessons l
           JOIN units u ON u.id = l.unit_id
           WHERE u.hsk_level IN (%s)""" % ",".join("?" * len(cleared)),
        cleared,
    ).fetchall()
    for row in rows:
        conn.execute(
            """INSERT INTO lesson_progress
                 (lesson_id, completed, best_score, unlocked, completed_at)
               VALUES (?, 1, NULL, 1, datetime('now'))
               ON CONFLICT(lesson_id) DO UPDATE SET completed = 1, unlocked = 1,
                 completed_at = COALESCE(lesson_progress.completed_at, datetime('now'))""",
            (row["id"],),
        )
    return cleared
