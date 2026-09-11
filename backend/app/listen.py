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
    pool: list[dict] = []
    for lesson in conn.execute("SELECT id, sentences, dialogue FROM lessons").fetchall():
        for s in json.loads(lesson["sentences"] or "[]"):
            hanzi = "".join(s.get("tokens", []))
            if hanzi and s.get("pinyin"):
                pool.append({"hanzi": hanzi, "pinyin": s["pinyin"], "gloss": s.get("gloss", "")})
        for line in json.loads(lesson["dialogue"] or "[]"):
            if line.get("hanzi") and line.get("pinyin"):
                pool.append({"hanzi": line["hanzi"], "pinyin": line["pinyin"], "gloss": line.get("gloss", "")})
    return pool


def dictation_item(conn: sqlite3.Connection) -> dict | None:
    pool = _dictation_pool(conn)
    if not pool:
        return None
    item = random.choice(pool)
    return {
        "hanzi": item["hanzi"],
        "pinyin": item["pinyin"],
        "gloss": item["gloss"],
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
