"""Pinyin → Zhuyin (注音符號 / bopomofo) conversion.

Zhuyin is Taiwan's phonetic notation, so the app offers it alongside pinyin
(settings.phonetic). Rather than hand-author a second reading for every word,
we derive zhuyin from the pinyin already in the content, once, at load time.

Two problems make this more than a table lookup:

1. **Segmentation.** As `tones.py` documents, content pinyin is written
   word-grouped ("biànlì shāngdiàn"), so spaces do not delimit syllables. We
   search for *every* valid way to cut a word into syllables and, when the
   caller supplies the hanzi, keep the segmentation whose syllable count matches
   the character count. Ambiguity like "xian" (xian vs. xi-an) is then resolved
   by the characters themselves.

2. **Orthography.** Pinyin spelling hides several finals: `-iu` is really
   `-iou`, `-ui` is `-uei`, `-un` is `-uen`, `-ong` is ㄨㄥ, `-iong` is ㄩㄥ, the
   `u` after j/q/x is really `ü`, and the `i` in zhi/chi/shi/ri/zi/ci/si is not a
   vowel at all. Those are handled explicitly below.

When a syllable cannot be converted, or the count check fails, we return None —
callers keep pinyin rather than show a wrong reading.
"""

from __future__ import annotations

import re
import unicodedata

from .textdiff import _TONE_MARKS
from .tones import han_syllable_count

# --- Tone notation -----------------------------------------------------------
# Tone 1 is unmarked. Tones 2–4 follow the syllable; the neutral tone is a dot
# that precedes it (˙ㄉㄜ), which is why this is applied positionally below.
TONE2 = "ˊ"  # ˊ
TONE3 = "ˇ"  # ˇ
TONE4 = "ˋ"  # ˋ
TONE5 = "˙"  # ˙
_TONE_SUFFIX = {1: "", 2: TONE2, 3: TONE3, 4: TONE4}

# --- Symbol tables -----------------------------------------------------------
_INITIALS = {
    "b": "ㄅ", "p": "ㄆ", "m": "ㄇ", "f": "ㄈ",
    "d": "ㄉ", "t": "ㄊ", "n": "ㄋ", "l": "ㄌ",
    "g": "ㄍ", "k": "ㄎ", "h": "ㄏ",
    "j": "ㄐ", "q": "ㄑ", "x": "ㄒ",
    "zh": "ㄓ", "ch": "ㄔ", "sh": "ㄕ", "r": "ㄖ",
    "z": "ㄗ", "c": "ㄘ", "s": "ㄙ",
}
# Longest-first, so "zh" wins over "z".
_INITIAL_KEYS = sorted(_INITIALS, key=len, reverse=True)

# Finals, keyed by their *underlying* form (after the normalisations in
# `_normalise_final`), not their surface pinyin spelling.
_FINALS = {
    "a": "ㄚ", "o": "ㄛ", "e": "ㄜ", "ê": "ㄝ",
    "ai": "ㄞ", "ei": "ㄟ", "ao": "ㄠ", "ou": "ㄡ",
    "an": "ㄢ", "en": "ㄣ", "ang": "ㄤ", "eng": "ㄥ", "er": "ㄦ",

    "i": "ㄧ", "ia": "ㄧㄚ", "ie": "ㄧㄝ", "iao": "ㄧㄠ", "iou": "ㄧㄡ",
    "ian": "ㄧㄢ", "in": "ㄧㄣ", "iang": "ㄧㄤ", "ing": "ㄧㄥ", "iong": "ㄩㄥ",

    "u": "ㄨ", "ua": "ㄨㄚ", "uo": "ㄨㄛ", "uai": "ㄨㄞ", "uei": "ㄨㄟ",
    "uan": "ㄨㄢ", "uen": "ㄨㄣ", "uang": "ㄨㄤ", "ueng": "ㄨㄥ", "ong": "ㄨㄥ",

    "ü": "ㄩ", "üe": "ㄩㄝ", "üan": "ㄩㄢ", "ün": "ㄩㄣ",
}

# Zero-initial syllables. Pinyin respells these with y/w, and the respelling is
# not a simple prefix swap (you→ㄧㄡ, wei→ㄨㄟ, yong→ㄩㄥ), so they are listed.
_ZERO_INITIAL = {
    "yi": "ㄧ", "ya": "ㄧㄚ", "ye": "ㄧㄝ", "yao": "ㄧㄠ", "you": "ㄧㄡ",
    "yan": "ㄧㄢ", "yin": "ㄧㄣ", "yang": "ㄧㄤ", "ying": "ㄧㄥ", "yong": "ㄩㄥ",

    "wu": "ㄨ", "wa": "ㄨㄚ", "wo": "ㄨㄛ", "wai": "ㄨㄞ", "wei": "ㄨㄟ",
    "wan": "ㄨㄢ", "wen": "ㄨㄣ", "wang": "ㄨㄤ", "weng": "ㄨㄥ",

    "yu": "ㄩ", "yue": "ㄩㄝ", "yuan": "ㄩㄢ", "yun": "ㄩㄣ",

    "a": "ㄚ", "o": "ㄛ", "e": "ㄜ", "ê": "ㄝ", "ai": "ㄞ", "ei": "ㄟ",
    "ao": "ㄠ", "ou": "ㄡ", "an": "ㄢ", "en": "ㄣ", "ang": "ㄤ", "eng": "ㄥ",
    "er": "ㄦ",
}

# After these initials, a written "i" is the syllabic (empty) final: zhi = ㄓ.
_EMPTY_FINAL_INITIALS = {"zh", "ch", "sh", "r", "z", "c", "s"}

_PUNCT_RE = re.compile(r"[^a-zêü]", re.IGNORECASE)


def _normalise_final(initial: str, final: str) -> str:
    """Map a surface pinyin final onto the underlying final used by _FINALS."""
    # ü is written plain "u" after j/q/x (and often typed as "v" elsewhere).
    final = final.replace("v", "ü")
    if initial in ("j", "q", "x") and final.startswith("u"):
        final = "ü" + final[1:]
    # Abbreviated spellings.
    if final == "iu":
        return "iou"
    if final == "ui":
        return "uei"
    if final == "un":
        return "ün" if initial in ("j", "q", "x") else "uen"
    return final


def syllable_to_zhuyin(syllable: str, tone: int) -> str | None:
    """Convert one toneless pinyin syllable + tone number to zhuyin.

    Returns None if the syllable is not valid pinyin.
    """
    s = syllable.lower()
    if not s:
        return None

    base = _ZERO_INITIAL.get(s)
    if base is None:
        for key in _INITIAL_KEYS:
            if s.startswith(key):
                rest = s[len(key) :]
                if not rest:
                    return None
                if rest == "i" and key in _EMPTY_FINAL_INITIALS:
                    base = _INITIALS[key]
                else:
                    tail = _FINALS.get(_normalise_final(key, rest))
                    if tail is None:
                        return None
                    base = _INITIALS[key] + tail
                break
    if base is None:
        return None

    if tone == 5:
        return TONE5 + base
    return base + _TONE_SUFFIX.get(tone, "")


def _is_syllable(s: str) -> bool:
    return syllable_to_zhuyin(s, 1) is not None


def _segmentations(letters: str, limit: int = 64) -> list[list[tuple[int, int]]]:
    """Every way to cut `letters` into valid pinyin syllables.

    Returned as (start, end) spans so the caller can recover tone positions.
    Longer syllables are tried first, so the greedy reading sorts first.
    """
    results: list[list[tuple[int, int]]] = []

    def walk(pos: int, acc: list[tuple[int, int]]) -> None:
        if len(results) >= limit:
            return
        if pos == len(letters):
            results.append(list(acc))
            return
        for end in range(min(len(letters), pos + 6), pos, -1):
            if _is_syllable(letters[pos:end]):
                acc.append((pos, end))
                walk(end, acc)
                acc.pop()

    walk(0, [])
    return results


def _scan(text: str) -> tuple[str, list[int]]:
    """Split a pinyin run into base letters plus the tone at each letter index."""
    letters: list[str] = []
    tones: list[int] = []
    for ch in unicodedata.normalize("NFC", text):
        if ch in _TONE_MARKS:
            base, tone = _TONE_MARKS[ch]
            letters.append("ü" if base == "v" else base)
            tones.append(tone)
        elif ch.isdigit():
            # Numeric tone applies to the syllable just written.
            if tones and ch in "12345":
                tones[-1] = int(ch)
        else:
            letters.append(ch.lower())
            tones.append(0)
    return "".join(letters), tones


def _convert_run(run: str, expect: int | None) -> str | None:
    """Convert one uninterrupted run of pinyin letters."""
    letters, tones = _scan(run)
    if not letters:
        return None

    options = _segmentations(letters)
    if not options:
        return None
    if expect is not None:
        options = [o for o in options if len(o) == expect]
        if not options:
            return None

    spans = options[0]
    out: list[str] = []
    for start, end in spans:
        marked = [t for t in tones[start:end] if t]
        tone = marked[0] if marked else 5
        z = syllable_to_zhuyin(letters[start:end], tone)
        if z is None:
            return None
        out.append(z)
    return " ".join(out)


def to_zhuyin(pinyin: str, hanzi: str | None = None) -> str | None:
    """Convert a pinyin string to zhuyin, or None if it cannot be done safely.

    `hanzi`, when given, pins the expected syllable count (one per Han
    character), which resolves segmentation ambiguity and catches mismatched
    content. Punctuation and spacing in `pinyin` are preserved; every syllable is
    separated by a space.
    """
    if not pinyin or not pinyin.strip():
        return None

    text = unicodedata.normalize("NFC", pinyin)
    runs: list[str] = []
    seps: list[str] = []
    cur: list[str] = []
    for ch in text:
        if _PUNCT_RE.match(ch) and ch not in _TONE_MARKS and not ch.isdigit():
            runs.append("".join(cur))
            cur = []
            seps.append(ch)
        else:
            cur.append(ch)
    runs.append("".join(cur))

    expect = han_syllable_count(hanzi) if hanzi else None
    # A single run can be pinned exactly; across several runs we only pin the
    # total, so convert each run freely and check the sum afterwards.
    nonempty = [r for r in runs if r.strip()]
    if not nonempty:
        return None

    converted: list[str | None] = []
    if expect is not None and len(nonempty) == 1:
        converted = [_convert_run(r, expect) if r.strip() else "" for r in runs]
    else:
        converted = [_convert_run(r, None) if r.strip() else "" for r in runs]

    if any(c is None for c in converted):
        return None

    if expect is not None:
        total = sum(len(c.split()) for c in converted if c)
        if total != expect:
            return None

    out: list[str] = []
    for i, c in enumerate(converted):
        out.append(c or "")
        if i < len(seps):
            out.append(seps[i])
    return "".join(out).strip()
