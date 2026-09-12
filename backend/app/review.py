"""Build review-queue items and run the placement check (spec §3.2).

A single SRS card schedules one vocab item; its *presentation* rotates across
review kinds (recognition / recall / audio→meaning / cloze) so the learner sees
the word from several angles. Rating (Again/Hard/Good/Easy) drives FSRS.
"""

from __future__ import annotations

import random
import sqlite3

from . import content, srs
from .exercises import _distractor_glosses, _distractor_words, _mc, short_gloss

# Review render kinds in rotation. cloze only applies when the item has an
# example sentence containing the word.
_ROTATION = ["recognition", "audio_meaning", "recall", "cloze"]

# Grammar points rotate through drills that suit a pattern rather than a word
# (spec §3.3): recall the pattern, pick the right particle out of a model
# sentence, and reorder one. A grammar point is not a flashcard — "what does 了
# mean" is not the thing worth being able to do with it.
_GRAMMAR_ROTATION = ["pattern_recall", "particle_cloze", "pattern_build"]

# Particles and function words a grammar drill may blank out. Restricted on
# purpose: blanking a content word tests vocabulary, which the vocab cards
# already do, and tells you nothing about whether the pattern is understood.
PARTICLES = (
    "了", "的", "得", "地", "著", "過", "嗎", "呢", "吧", "啊", "喔", "耶", "啦",
    "在", "把", "被", "比", "跟", "和", "或", "還是", "就", "才", "都", "也",
    "很", "太", "最", "會", "要", "能", "可以", "應該", "給", "往", "用", "只",
    "有沒有", "快要", "一邊", "到", "從", "對", "為", "讓", "幫",
)


def _vocab_row(conn: sqlite3.Connection, vocab_id: str) -> dict | None:
    r = conn.execute("SELECT * FROM vocab WHERE id = ?", (vocab_id,)).fetchone()
    return dict(r) if r else None


def _pool(conn: sqlite3.Connection) -> list[dict]:
    return content.all_vocab(conn)


def _render(card: sqlite3.Row, v: dict, pool: list[dict], kind: str) -> dict:
    rng = random.Random(f"{card['id']}:{card['reps']}:{kind}")
    trad = v["traditional"]
    gloss = short_gloss(v["gloss"])

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


def _grammar_row(conn: sqlite3.Connection, grammar_id: str) -> dict | None:
    r = conn.execute("SELECT * FROM grammar WHERE id = ?", (grammar_id,)).fetchone()
    return content._grammar_dict(r) if r else None


def _pattern_particles(g: dict) -> list[str]:
    """Particles that actually appear in this point's pattern or title.

    Longest first, so 有沒有 is matched before 有 and 還是 before 是 — otherwise
    a multi-character particle gets blanked one character at a time.
    """
    text = f"{g.get('pattern', '')}{g.get('title', '')}"
    found = [p for p in PARTICLES if p in text]
    return sorted(found, key=len, reverse=True)


def _render_grammar(
    card: sqlite3.Row, g: dict, patterns: list[str], kind: str
) -> dict | None:
    """One grammar review item, or None when this point can't support this kind."""
    rng = random.Random(f"{card['id']}:{card['reps']}:{kind}")
    examples = [e for e in (g.get("examples") or []) if e.get("hanzi")]

    if kind == "pattern_recall":
        # Given the explanation, pick the pattern. Distractors are other points'
        # patterns, so the choice is between real alternatives.
        others = [p for p in patterns if p != g["pattern"]]
        rng.shuffle(others)
        return {
            "kind": "pattern_recall",
            "grammar_id": g["id"],
            "title": g["title"],
            "explanation": g["explanation"],
            "answer": g["pattern"],
            "options": _mc(g["pattern"], others[:3], rng),
        }

    if kind == "particle_cloze" and examples:
        particles = _pattern_particles(g)
        for ex in rng.sample(examples, len(examples)):
            for particle in particles:
                if particle in ex["hanzi"]:
                    masked = ex["hanzi"].replace(particle, "＿", 1)
                    distractors = [p for p in PARTICLES if p != particle]
                    rng.shuffle(distractors)
                    return {
                        "kind": "particle_cloze",
                        "grammar_id": g["id"],
                        "title": g["title"],
                        "masked": masked,
                        "audio_text": ex["hanzi"],
                        "gloss": ex.get("gloss"),
                        "answer": particle,
                        "options": _mc(particle, distractors[:3], rng),
                    }
        return None

    if kind == "pattern_build" and examples:
        ex = rng.choice(examples)
        tokens = _tokenize(ex["hanzi"], _pattern_particles(g))
        if len(tokens) < 3:
            return None
        shuffled = tokens[:]
        while shuffled == tokens:
            rng.shuffle(shuffled)
        return {
            "kind": "pattern_build",
            "grammar_id": g["id"],
            "title": g["title"],
            "pattern": g["pattern"],
            "gloss": ex.get("gloss"),
            "audio_text": ex["hanzi"],
            "tokens": shuffled,
            "answer": tokens,
        }

    return None


def _tokenize(hanzi: str, particles: list[str]) -> list[str]:
    """Split a model sentence into tiles, keeping each particle its own tile.

    Crude on purpose — no segmenter, since the point is only to produce
    reorderable chunks where the particle is one of them. Everything between
    particles stays together, which is usually a word or short phrase.
    """
    text = "".join(c for c in hanzi if c not in "。，？！、：；「」")
    tokens: list[str] = []
    buf = ""
    i = 0
    while i < len(text):
        hit = next((p for p in particles if text.startswith(p, i)), None)
        if hit:
            if buf:
                tokens.append(buf)
                buf = ""
            tokens.append(hit)
            i += len(hit)
        else:
            buf += text[i]
            i += 1
    if buf:
        tokens.append(buf)
    return tokens


def _choose_kind(card: sqlite3.Row, v: dict) -> str:
    kind = _ROTATION[card["reps"] % len(_ROTATION)]
    if kind == "cloze" and not (v.get("example_hanzi") and v["traditional"] in v["example_hanzi"]):
        return "recognition"
    return kind


def build_queue(conn: sqlite3.Connection, new_limit: int) -> list[dict]:
    """Today's review items — vocabulary and grammar alike (spec §3.6).

    Grammar cards used to be silently dropped here, so a grammar point was
    taught once and never seen again despite §3.6 scheduling it like any other
    item. A point that cannot render one of its drills (no model sentences yet,
    say) is skipped for this rep rather than failing the queue.
    """
    pool = _pool(conn)
    patterns = [r["pattern"] for r in conn.execute("SELECT pattern FROM grammar")]
    cards = srs.due_cards(conn, new_limit)

    items: list[dict] = []
    for card in cards:
        base = {
            "card_id": card["id"],
            "item_id": card["item_id"],
            "item_type": card["item_type"],
            "reps": card["reps"],
            "state": card["state"],
        }

        if card["item_type"] == "vocab":
            v = _vocab_row(conn, card["item_id"])
            if not v:
                continue
            items.append({**base, **_render(card, v, pool, _choose_kind(card, v))})
            continue

        if card["item_type"] == "grammar":
            g = _grammar_row(conn, card["item_id"])
            if not g:
                continue
            rendered = _render_grammar_rotating(card, g, patterns)
            if rendered:
                items.append({**base, **rendered})

    return items


def _render_grammar_rotating(card: sqlite3.Row, g: dict, patterns: list[str]) -> dict | None:
    """Try this rep's drill, then the others, so a point is never unreviewable."""
    start = card["reps"] % len(_GRAMMAR_ROTATION)
    for offset in range(len(_GRAMMAR_ROTATION)):
        kind = _GRAMMAR_ROTATION[(start + offset) % len(_GRAMMAR_ROTATION)]
        rendered = _render_grammar(card, g, patterns, kind)
        if rendered:
            return rendered
    return None


# Placement moved to app/placement.py when it became an adaptive, multi-band
# walk across HSK 1-4 with listening and sentence-building items (spec §3.1).
