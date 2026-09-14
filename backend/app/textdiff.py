"""Dictation diffing (spec §3.3, testing expectations §7).

Produces a diff-highlighted comparison between what the learner typed and the
target sentence, for both Chinese-character input and pinyin input. The result
is a list of segments the frontend renders (equal / wrong / missing / extra).
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

_HAN_RE = re.compile(r"[㐀-䶿一-鿿]")
_DROP_RE = re.compile(r"[\s，。？！、,.?!;:'\"()（）]")

# Pinyin tone-mark → (base vowel, tone number).
_TONE_MARKS = {
    "ā": ("a", 1), "á": ("a", 2), "ǎ": ("a", 3), "à": ("a", 4),
    "ē": ("e", 1), "é": ("e", 2), "ě": ("e", 3), "è": ("e", 4),
    "ī": ("i", 1), "í": ("i", 2), "ǐ": ("i", 3), "ì": ("i", 4),
    "ō": ("o", 1), "ó": ("o", 2), "ǒ": ("o", 3), "ò": ("o", 4),
    "ū": ("u", 1), "ú": ("u", 2), "ǔ": ("u", 3), "ù": ("u", 4),
    "ǖ": ("v", 1), "ǘ": ("v", 2), "ǚ": ("v", 3), "ǜ": ("v", 4),
}


def has_han(text: str) -> bool:
    return bool(_HAN_RE.search(text or ""))


def _clean_han(text: str) -> str:
    return _DROP_RE.sub("", text or "")


def strip_tones(pinyin: str) -> str:
    """Remove tone marks/numbers from a pinyin string, keeping base letters."""
    out = []
    for ch in unicodedata.normalize("NFC", pinyin or ""):
        if ch in _TONE_MARKS:
            out.append(_TONE_MARKS[ch][0])
        elif ch.isdigit():
            continue
        else:
            out.append(ch)
    return "".join(out)


def syllables(pinyin: str, tone_sensitive: bool = True) -> list[str]:
    """Split a (space-separated) pinyin string into normalised syllables."""
    raw = _DROP_RE.sub(" ", pinyin or "").lower().split()
    if tone_sensitive:
        return [unicodedata.normalize("NFC", s) for s in raw if s]
    return [strip_tones(s) for s in raw if s]


def _segments(exp: list[str], got: list[str], join: str) -> list[dict]:
    sm = SequenceMatcher(None, exp, got, autojunk=False)
    segments: list[dict] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            segments.append({"type": "equal", "text": join.join(exp[i1:i2])})
        elif tag == "delete":  # in target, missing from the answer
            segments.append({"type": "missing", "text": join.join(exp[i1:i2])})
        elif tag == "insert":  # typed but not in the target
            segments.append({"type": "extra", "text": join.join(got[j1:j2])})
        elif tag == "replace":
            segments.append({
                "type": "wrong",
                "expected": join.join(exp[i1:i2]),
                "got": join.join(got[j1:j2]),
            })
    return segments


def han_diff(expected: str, answer: str) -> dict:
    exp = list(_clean_han(expected))
    got = list(_clean_han(answer))
    return {
        "mode": "han",
        "correct": exp == got,
        "segments": _segments(exp, got, ""),
    }


def pinyin_diff(expected: str, answer: str, tone_sensitive: bool = True) -> dict:
    exp = syllables(expected, tone_sensitive)
    got = syllables(answer, tone_sensitive)
    return {
        "mode": "pinyin",
        "tone_sensitive": tone_sensitive,
        "correct": exp == got,
        "segments": _segments(exp, got, " "),
    }


def dictation_check(
    expected_hanzi: str,
    expected_pinyin: str,
    answer: str,
    tone_sensitive: bool = True,
) -> dict:
    """Diff an answer against the target, auto-selecting han vs pinyin mode
    from whether the answer contains Chinese characters."""
    if has_han(answer):
        return han_diff(expected_hanzi, answer)
    return pinyin_diff(expected_pinyin, answer, tone_sensitive)
