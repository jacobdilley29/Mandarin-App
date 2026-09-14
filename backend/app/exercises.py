"""Build a lesson's exercise stream (spec §3.1).

Given a lesson's content and a distractor pool, produce an ordered list of
exercises: intro cards, grammar cards, a mix of drills (all non-speaking types),
and a dialogue playthrough. The speak-check card (§3.1 step 5) is deferred to
Phase 4.

Generation is deterministic per lesson (seeded RNG) so a lesson looks the same
each time it's opened, but distractors/orderings vary between items.

Gradable drill kinds (used to compute the lesson score):
    match, audio_meaning, char_recognition, cloze, tile_build, listen_type, translate
Non-gradable: vocab_intro, grammar, dialogue.

`listen_type` is a historical name: the drill is built from tiles now, not
typed. The string is kept because it is what `drill_results.kind` already
holds, and renaming it would split that history for no gain.
"""

from __future__ import annotations

import random

from . import zhuyin

GRADABLE_KINDS = {
    "match", "audio_meaning", "char_recognition", "cloze", "particle_cloze",
    "tile_build", "listen_type", "translate",
}


# CC-CEDICT glosses are reference entries, not answer options. 有 comes through
# as "to have; there is; (bound form) having; with; -ful; -ed; -al (as in 意
# intentional)" — unreadable in a multiple-choice button, and it gives the answer
# away by being four times longer than the distractors. Hand-authored glosses are
# already short, so this only bites on the imported vocabulary.
MAX_GLOSS_SENSES = 2
MAX_GLOSS_CHARS = 48


def short_gloss(gloss: str | None) -> str:
    """The first sense or two of a dictionary gloss, trimmed for a button."""
    if not gloss:
        return ""
    senses = [g.strip() for g in gloss.split(";") if g.strip()]
    if not senses:
        return gloss.strip()

    out = senses[0]
    for extra in senses[1:MAX_GLOSS_SENSES]:
        candidate = f"{out}; {extra}"
        if len(candidate) > MAX_GLOSS_CHARS:
            break
        out = candidate

    if len(out) > MAX_GLOSS_CHARS:
        out = out[:MAX_GLOSS_CHARS].rsplit(" ", 1)[0].rstrip(",;") + "…"
    return out


def _rng(lesson_id: str, salt: str = "") -> random.Random:
    return random.Random(f"{lesson_id}:{salt}")


def _distractor_glosses(pool: list[dict], correct_id: str, n: int, rng: random.Random) -> list[str]:
    others = [short_gloss(v["gloss"]) for v in pool if v["id"] != correct_id]
    rng.shuffle(others)
    # De-dup while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for g in others:
        if g not in seen:
            seen.add(g)
            out.append(g)
        if len(out) >= n:
            break
    return out


def _distractor_words(pool: list[dict], correct: str, n: int, rng: random.Random) -> list[str]:
    others = [v["traditional"] for v in pool if v["traditional"] != correct]
    rng.shuffle(others)
    seen: set[str] = set()
    out: list[str] = []
    for w in others:
        if w not in seen:
            seen.add(w)
            out.append(w)
        if len(out) >= n:
            break
    return out


def _confusable_words(pool: list[dict], correct: str, n: int, rng: random.Random) -> list[str]:
    """Distractors that are actually hard to tell apart from `correct`.

    Character recognition is only a test of recognition if the wrong answers are
    plausible. Random words make it a test of nothing — the right glyph stands
    out at a glance. So words sharing a character with the target come first
    (內用/外帶, 早上/晚上), then words of the same length, then anything.
    """
    others = [v["traditional"] for v in pool if v["traditional"] != correct]
    rng.shuffle(others)

    chars = set(correct)
    shares = [w for w in others if chars & set(w)]
    same_length = [w for w in others if len(w) == len(correct) and w not in shares]
    rest = [w for w in others if w not in shares and w not in same_length]

    out: list[str] = []
    for bucket in (shares, same_length, rest):
        for w in bucket:
            if w not in out:
                out.append(w)
            if len(out) >= n:
                return out
    return out


# --- Tiles -----------------------------------------------------------------
#
# A tile is a word plus the reading printed under it, in pinyin or 注音 as the
# Me tab asks. The reading is attached here, server-side, because it has to be
# split out of the sentence's own pinyin — see zhuyin.for_tokens for why that
# pinyin, and not the characters, is the source of truth.


def _tiles(tokens: list[str], pinyin: str) -> list[dict]:
    """The sentence's tokens as tiles, each carrying its own reading."""
    return zhuyin.for_tokens(tokens, pinyin)


def _loose_tiles(words: list[str], pool: list[dict]) -> list[dict]:
    """Decoy tiles, read from the vocabulary rather than from a sentence."""
    by_word = {v["traditional"]: v for v in pool}
    out: list[dict] = []
    for w in words:
        v = by_word.get(w, {})
        rows = zhuyin.for_tokens([w], v.get("pinyin") or "")
        out.append(rows[0] if rows else {"text": w, "pinyin": None, "zhuyin": None})
    return out


# How many wrong words join the rack in a dictation drill. Without them every
# tile belongs in the answer, so the exercise asks the learner to order words
# they were handed rather than to recognise the ones they heard.
DICTATION_DECOYS = 4


def _mc(options_correct: str, distractors: list[str], rng: random.Random) -> list[dict]:
    opts = [{"text": options_correct, "correct": True}] + [
        {"text": d, "correct": False} for d in distractors
    ]
    rng.shuffle(opts)
    return opts


# Particles and function words a grammar drill may blank. Restricted on purpose:
# blanking a content word tests vocabulary, not the pattern. Kept in step with
# review.PARTICLES, which tests assert.
PARTICLES = (
    "了", "的", "得", "地", "著", "過", "嗎", "呢", "吧", "啊", "喔", "耶", "啦",
    "在", "把", "被", "比", "跟", "和", "或", "還是", "就", "才", "都", "也",
    "很", "太", "最", "會", "要", "能", "可以", "應該", "給", "往", "用", "只",
    "有沒有", "快要", "一邊", "到", "從", "對", "為", "讓", "幫",
)


def _particle_cloze(g: dict, sentences: list[dict], rng: random.Random) -> dict | None:
    """Blank this grammar point's particle out of a sentence that uses it.

    Longest particle first, so 有沒有 wins over 有 and 還是 over 是 — otherwise a
    multi-character particle is blanked one character at a time and the drill
    becomes nonsense.
    """
    marks = sorted(
        (p for p in PARTICLES if p in f"{g.get('pattern', '')}{g.get('title', '')}"),
        key=len,
        reverse=True,
    )
    if not marks:
        return None

    for s in sentences:
        sent = "".join(s.get("tokens") or [])
        for particle in marks:
            if particle not in sent:
                continue
            distractors = [p for p in PARTICLES if p != particle]
            rng.shuffle(distractors)
            return {
                "grammar_id": g["id"],
                "title": g["title"],
                "pattern": g["pattern"],
                "masked": sent.replace(particle, "＿", 1),
                "audio_text": sent,
                "pinyin": s.get("pinyin"),
                "gloss": s.get("gloss"),
                "answer": particle,
                "options": _mc(particle, distractors[:3], rng),
            }
    return None


def build_stream(lesson: dict, pool: list[dict]) -> list[dict]:
    lid = lesson["id"]
    vocab = lesson["vocab"]
    grammar = lesson["grammar"]
    sentences = lesson["sentences"]
    stream: list[dict] = []
    idx = 0

    def add(kind: str, payload: dict) -> None:
        nonlocal idx
        stream.append({
            "id": f"{lid}-{idx}",
            "kind": kind,
            "gradable": kind in GRADABLE_KINDS,
            "payload": payload,
        })
        idx += 1

    # 1. Vocab intro cards.
    for v in vocab:
        add("vocab_intro", {
            "vocab_id": v["id"],
            "traditional": v["traditional"],
            "pinyin": v["pinyin"],
            "zhuyin": v.get("zhuyin"),
            "gloss": v["gloss"],
            "taiwan_note": v.get("taiwan_note"),
            "example": v.get("example"),
        })

    # 2. Grammar cards.
    for g in grammar:
        add("grammar", {
            "grammar_id": g["id"],
            "title": g["title"],
            "pattern": g["pattern"],
            "explanation": g["explanation"],
            "examples": g["examples"],
            "taiwan_note": g.get("taiwan_note"),
        })

    # 3a. One matching exercise over the lesson vocab (char ↔ meaning).
    if len(vocab) >= 2:
        rng = _rng(lid, "match")
        pairs = [{"vocab_id": v["id"], "traditional": v["traditional"], "gloss": v["gloss"]}
                 for v in vocab]
        rng.shuffle(pairs)
        # HelloChinese-style: cap a single board at 5 pairs.
        add("match", {"pairs": pairs[:5]})

    # 3b. audio → meaning (MC) for each vocab item.
    for v in vocab:
        rng = _rng(lid, f"am:{v['id']}")
        add("audio_meaning", {
            "vocab_id": v["id"],
            "audio_text": v["traditional"],
            "pinyin": v["pinyin"],
            "zhuyin": v.get("zhuyin"),
            "options": _mc(v["gloss"], _distractor_glosses(pool, v["id"], 3, rng), rng),
        })

    # 3b-ii. Character recognition (spec §3.2): meaning + sound given, pick the
    # right characters out of a set chosen to be genuinely confusable. This is
    # the one direction the other drills never test — every other exercise shows
    # the learner the characters and asks something about them.
    for v in vocab:
        rng = _rng(lid, f"cr:{v['id']}")
        add("char_recognition", {
            "vocab_id": v["id"],
            "gloss": v["gloss"],
            "pinyin": v["pinyin"],
            "zhuyin": v.get("zhuyin"),
            "audio_text": v["traditional"],
            "answer": v["traditional"],
            "options": _mc(
                v["traditional"], _confusable_words(pool, v["traditional"], 3, rng), rng
            ),
        })

    # 3b-iii. Particle cloze (spec §3.3): blank the grammar word out of one of
    # this lesson's own drill sentences. The vocab cloze above blanks a content
    # word, which tests vocabulary; this blanks 了/的/得/比 and tests whether the
    # pattern is understood — a different question about the same sentence.
    for g in grammar:
        rng = _rng(lid, f"pc:{g['id']}")
        item = _particle_cloze(g, sentences, rng)
        if item:
            add("particle_cloze", item)

    # 3c. Sentence drills: rotate cloze / tile_build / listen_type / translate.
    rotation = ["cloze", "tile_build", "translate", "listen_type"]
    for si, s in enumerate(sentences):
        kind = rotation[si % len(rotation)]
        tokens = s["tokens"]
        sent = "".join(tokens)
        rng = _rng(lid, f"{kind}:{si}")

        if kind == "cloze" and 0 <= s.get("cloze_index", -1) < len(tokens):
            ci = s["cloze_index"]
            answer = tokens[ci]
            display = tokens[:ci] + ["＿＿"] + tokens[ci + 1:]
            add("cloze", {
                "tokens": display,
                "pinyin": s.get("pinyin"),
                "gloss": s.get("gloss"),
                "audio_text": sent,
                "options": _mc(answer, _distractor_words(pool, answer, 3, rng), rng),
            })
        elif kind == "tile_build":
            shuffled = _tiles(tokens, s.get("pinyin") or "")
            rng.shuffle(shuffled)
            add("tile_build", {
                "tiles": shuffled,
                "answer": tokens,
                "pinyin": s.get("pinyin"),
                "gloss": s.get("gloss"),
                "audio_text": sent,
            })
        elif kind == "translate":
            add("translate", {
                "prompt_hanzi": sent,
                "pinyin": s.get("pinyin"),
                "audio_text": sent,
                "options": _mc(
                    s.get("gloss", ""),
                    _sentence_gloss_distractors(sentences, si, 3, rng),
                    rng,
                ),
            })
        elif kind == "listen_type":
            # Dictation: hear it, then build it from tiles. The rack is the
            # sentence's own words plus decoys, so hearing 水 and picking it
            # out of 水/茶/咖啡 is the exercise — which is what typing used to
            # ask for, minus the IME.
            decoys = [
                d for d in _distractor_words(pool, sent, DICTATION_DECOYS * 2, rng)
                if d not in tokens
            ][:DICTATION_DECOYS]
            rack = _tiles(tokens, s.get("pinyin") or "") + _loose_tiles(decoys, pool)
            rng.shuffle(rack)
            add("listen_type", {
                "audio_text": sent,
                "answer": tokens,
                "tiles": rack,
                "pinyin": s.get("pinyin"),
                "gloss": s.get("gloss"),
            })

    # 4. Dialogue playthrough (single exercise carrying all lines).
    if lesson["dialogue"]:
        add("dialogue", {"lines": lesson["dialogue"]})

    return stream


def _sentence_gloss_distractors(sentences: list[dict], correct_idx: int, n: int, rng: random.Random) -> list[str]:
    others = [s.get("gloss", "") for i, s in enumerate(sentences) if i != correct_idx and s.get("gloss")]
    rng.shuffle(others)
    seen: set[str] = set()
    out: list[str] = []
    for g in others:
        if g not in seen:
            seen.add(g)
            out.append(g)
        if len(out) >= n:
            break
    return out
