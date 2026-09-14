"""Listening exercises (spec §3.3): dictation, comprehension sets, tone drills.

Dictation sentences are drawn from the curriculum the learner has met; tone
items are generated from vocabulary; comprehension sets come from committed
content (content/listen.json). Audio is synthesised at request time by the
audio router, alternating the two zh-TW voices.
"""

from __future__ import annotations

import json
import random
import sqlite3

from . import dictionary, zhuyin
from .audio import VOICES
from .config import REPO_ROOT
from .tones import TONE_NAMES, han_syllable_count, tones_from_pinyin

LISTEN_PATH = REPO_ROOT / "content" / "listen.json"
_VOICES = sorted(VOICES)  # deterministic order for alternation


def _pick_voice(seed: str) -> str:
    return _VOICES[hash(seed) % len(_VOICES)]


def _load_sets() -> list[dict]:
    if not LISTEN_PATH.is_file():
        return []
    return json.loads(LISTEN_PATH.read_text(encoding="utf-8")).get("sets", [])


# ---------------------------------------------------------------------------
# Dictation
# ---------------------------------------------------------------------------
def _dictation_pool(conn: sqlite3.Connection) -> list[dict]:
    """Dictation candidates, each carrying the tokens its tiles are built from.

    The two sources have different shapes. A drill sentence is already a list of
    words. A dialogue line is one string, so it has to be segmented — which
    `dictionary.annotate` already does against the curriculum plus CC-CEDICT,
    for tap-to-define.
    """
    pool: list[dict] = []
    for lesson in conn.execute("SELECT id, sentences, dialogue FROM lessons").fetchall():
        for s in json.loads(lesson["sentences"] or "[]"):
            tokens = [t for t in s.get("tokens", []) if t.strip()]
            if tokens and s.get("pinyin"):
                pool.append({
                    "hanzi": "".join(tokens),
                    "tokens": tokens,
                    "pinyin": s["pinyin"],
                    "gloss": s.get("gloss", ""),
                })
        for line in json.loads(lesson["dialogue"] or "[]"):
            if line.get("hanzi") and line.get("pinyin"):
                pool.append({
                    "hanzi": line["hanzi"],
                    "tokens": None,  # segmented on demand; see dictation_item
                    "pinyin": line["pinyin"],
                    "gloss": line.get("gloss", ""),
                })
    return pool


def _segment(conn: sqlite3.Connection, hanzi: str) -> list[str]:
    """A line's Han words, punctuation dropped — punctuation is not a tile."""
    return [
        span["text"]
        for span in dictionary.annotate(conn, hanzi)
        if not span.get("plain") and span["text"].strip()
    ]


# Wrong words on the rack. Without them the drill is a word-order puzzle: every
# tile belongs in the answer, so the learner never has to recognise one.
DECOYS = 4


def _decoy_tiles(conn: sqlite3.Connection, avoid: set[str], seed: str) -> list[dict]:
    rows = conn.execute(
        "SELECT traditional, pinyin FROM vocab ORDER BY id"
    ).fetchall()
    candidates = [r for r in rows if r["traditional"] not in avoid]
    rng = random.Random(seed)
    rng.shuffle(candidates)

    out: list[dict] = []
    seen: set[str] = set()
    for r in candidates:
        word = r["traditional"]
        if word in seen:
            continue
        seen.add(word)
        tile = zhuyin.for_tokens([word], r["pinyin"] or "")
        out.append(tile[0] if tile else {"text": word, "pinyin": None, "zhuyin": None})
        if len(out) >= DECOYS:
            break
    return out


def dictation_item(conn: sqlite3.Connection) -> dict | None:
    pool = _dictation_pool(conn)
    if not pool:
        return None
    item = random.choice(pool)

    tokens = item["tokens"] or _segment(conn, item["hanzi"])
    if not tokens:
        return None

    tiles = zhuyin.for_tokens(tokens, item["pinyin"])
    tiles += _decoy_tiles(conn, set(tokens), item["hanzi"])
    random.Random(item["hanzi"]).shuffle(tiles)

    return {
        "hanzi": item["hanzi"],
        "pinyin": item["pinyin"],
        "gloss": item["gloss"],
        "answer": tokens,
        "tiles": tiles,
        "audio_text": item["hanzi"],
        "voice": _pick_voice(item["hanzi"]),
    }


# ---------------------------------------------------------------------------
# Comprehension sets
# ---------------------------------------------------------------------------
def comprehension_set(set_id: str | None = None) -> dict | None:
    sets = _load_sets()
    if not sets:
        return None
    chosen = next((s for s in sets if s["id"] == set_id), None) if set_id else random.choice(sets)
    if not chosen:
        return None
    # Attach a voice per speaker so the two-party dialogue alternates voices.
    speakers = {}
    lines = []
    for i, line in enumerate(chosen["dialogue"]):
        sp = line["speaker"]
        if sp not in speakers:
            speakers[sp] = _VOICES[len(speakers) % len(_VOICES)]
        lines.append({**line, "audio_text": line["hanzi"], "voice": speakers[sp]})
    return {
        "id": chosen["id"],
        "title": chosen["title"],
        "hsk_level": chosen.get("hsk_level"),
        "dialogue": lines,
        "questions": chosen["questions"],
    }


def list_sets() -> list[dict]:
    return [{"id": s["id"], "title": s["title"], "hsk_level": s.get("hsk_level")} for s in _load_sets()]


# ---------------------------------------------------------------------------
# Tone ear-training
# ---------------------------------------------------------------------------
def _tone_pool(conn: sqlite3.Connection, n_syllables: int) -> list[dict]:
    pool = []
    for v in conn.execute("SELECT traditional, pinyin FROM vocab").fetchall():
        n_han = han_syllable_count(v["traditional"])
        tones = tones_from_pinyin(v["pinyin"])
        # Include a word only when its Han-character count matches the number of
        # tone-marked syllables — i.e. every syllable is toned 1–4 (no neutral),
        # so the drill is unambiguous.
        if n_han == n_syllables and len(tones) == n_syllables and all(1 <= t <= 4 for t in tones):
            pool.append({"traditional": v["traditional"], "pinyin": v["pinyin"], "tones": tones})
    return pool


def tone_item(conn: sqlite3.Connection, mode: str = "single") -> dict | None:
    n = 2 if mode == "pair" else 1
    pool = _tone_pool(conn, n)
    if not pool:
        return None
    item = random.choice(pool)
    rng = random.Random(item["traditional"])
    tones = item["tones"]

    if mode == "pair":
        correct = tuple(tones)
        all_pairs = [(a, b) for a in (1, 2, 3, 4) for b in (1, 2, 3, 4) if (a, b) != correct]
        rng.shuffle(all_pairs)
        options = [{"tones": list(correct), "correct": True}] + [
            {"tones": list(p), "correct": False} for p in all_pairs[:3]
        ]
        rng.shuffle(options)
    else:
        correct = tones[0]
        options = [{"tone": t, "correct": t == correct, "name": TONE_NAMES[t]} for t in (1, 2, 3, 4)]

    return {
        "mode": mode,
        "audio_text": item["traditional"],
        "traditional": item["traditional"],
        "pinyin": item["pinyin"],
        "tones": tones,
        "voice": _pick_voice(item["traditional"]),
        "options": options,
    }
