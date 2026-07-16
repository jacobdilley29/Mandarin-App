"""Build a lesson's exercise stream (spec §3.1).

Given a lesson's content and a distractor pool, produce an ordered list of
exercises: intro cards, grammar cards, a mix of drills (all non-speaking types),
and a dialogue playthrough. The speak-check card (§3.1 step 5) is deferred to
Phase 4.

Generation is deterministic per lesson (seeded RNG) so a lesson looks the same
each time it's opened, but distractors/orderings vary between items.

Gradable drill kinds (used to compute the lesson score):
    match, audio_meaning, cloze, tile_build, listen_type, translate
Non-gradable: vocab_intro, grammar, dialogue.
"""

from __future__ import annotations

import random

GRADABLE_KINDS = {
    "match", "audio_meaning", "cloze", "tile_build", "listen_type", "translate"
}


def _rng(lesson_id: str, salt: str = "") -> random.Random:
    return random.Random(f"{lesson_id}:{salt}")


def _distractor_glosses(pool: list[dict], correct_id: str, n: int, rng: random.Random) -> list[str]:
    others = [v["gloss"] for v in pool if v["id"] != correct_id]
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


def _mc(options_correct: str, distractors: list[str], rng: random.Random) -> list[dict]:
    opts = [{"text": options_correct, "correct": True}] + [
        {"text": d, "correct": False} for d in distractors
    ]
    rng.shuffle(opts)
    return opts


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
            "options": _mc(v["gloss"], _distractor_glosses(pool, v["id"], 3, rng), rng),
        })

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
            shuffled = list(tokens)
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
            add("listen_type", {
                "audio_text": sent,
                "answer": sent,
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
