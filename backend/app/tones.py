"""Tone extraction from pinyin, for tone ear-training (spec §3.3).

Pinyin in the content is written word-grouped (e.g. "biànlì shāngdiàn"), so we
cannot split on spaces to count syllables. Instead we scan the string for
tone-marked vowels — one per toned syllable — and rely on the caller to match
that against the Han-character count (each character is one syllable).
"""

from __future__ import annotations

import re
import unicodedata

from .textdiff import _TONE_MARKS

TONE_NAMES = {1: "high flat", 2: "rising", 3: "dipping", 4: "falling", 5: "neutral"}

_HAN_RE = re.compile(r"[㐀-䶿一-鿿]")


def han_syllable_count(traditional: str) -> int:
    """Number of syllables = number of Han characters."""
    return len(_HAN_RE.findall(traditional or ""))


def tones_from_pinyin(pinyin: str) -> list[int]:
    """One tone (1–4) per tone-marked vowel, in order.

    Neutral (unmarked) syllables are not represented — callers that need a tone
    per syllable should restrict themselves to words where every syllable is
    marked (see `listen._tone_pool`).
    """
    tones: list[int] = []
    for ch in unicodedata.normalize("NFC", pinyin or ""):
        if ch in _TONE_MARKS:
            tones.append(_TONE_MARKS[ch][1])
        elif ch.isdigit() and ch in "1234":
            tones.append(int(ch))
    return tones


def tone_of_syllable(syllable: str) -> int:
    """Tone 1–4 from a single syllable's diacritic, or 5 (neutral) if none."""
    t = tones_from_pinyin(syllable)
    return t[0] if t else 5


# The 20 tone pairs learners drill (tones 1–4 × 1–4, plus a few with neutral).
def tone_pairs() -> list[tuple[int, int]]:
    return [(a, b) for a in (1, 2, 3, 4) for b in (1, 2, 3, 4)]
