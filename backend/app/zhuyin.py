"""Zhuyin (注音符號 / bopomofo) for display beside pinyin.

Zhuyin is Taiwan's native phonetic system — what children learn, what keyboards
use, and what Taiwanese dictionaries print. An app about Taiwan Mandarin that
shows only Hanyu pinyin is showing the Mainland's answer to a Taiwanese
question, so the vocabulary card can show either, or both.

**Converted from this app's pinyin, never from the character.** That is the whole
design decision here. pypinyin can go straight from 銀行 to zhuyin, but it reads
it yínxíng; Taiwan says yínháng. Measured across the 1,208 words in the
curriculum, deriving from characters disagrees with the reading the app already
stores for **9.2%** of them — and the disagreements are precisely the readings
this app exists to get right: 和 hàn, 認識 rènshì, 誰 shéi, 東西 dōngxi. Since the
card shows pinyin and zhuyin side by side, a disagreement is not a subtle
internal inconsistency; it is two contradictory answers an inch apart.

So the pinyin is the source of truth and this only transcribes it. Taiwan
readings, sandhi and the overrides in content/taiwan_overrides.json are all
inherited for free, because they are already in the pinyin.

The neutral tone follows the Taiwan MOE convention: the dot goes **before** the
syllable (˙ㄉㄜ), where pypinyin and most Mainland sources put it after (ㄉㄜ˙).
"""

from __future__ import annotations

import functools
import re
import unicodedata

# Tone diacritics, which are stripped to find syllable boundaries. The diaeresis
# is deliberately NOT here: ü and u are different finals (綠 lǜ vs 路 lù), and
# dropping it would merge them.
_TONE_MARKS = {"̄", "́", "̌", "̀"}


@functools.lru_cache(maxsize=1)
def _syllables() -> frozenset[str]:
    """Every toneless Mandarin syllable pypinyin knows about (about 420)."""
    from pypinyin.constants import PINYIN_DICT

    out: set[str] = set()
    for readings in PINYIN_DICT.values():
        for reading in readings.split(","):
            plain = untone(reading).strip().lower()
            if plain and plain.replace("ü", "v").isalpha():
                out.add(plain)
    # The erhua suffix as the curriculum writes it: 一會兒 is stored "yī huì r",
    # a syllable pypinyin's own inventory has no entry for. syllable() maps it
    # to ˙ㄦ; without it here the tokeniser rejects the whole word.
    out.add("r")
    return frozenset(out)


def untone(text: str) -> str:
    """Drop tone marks, keep everything else — same length, ü intact."""
    decomposed = unicodedata.normalize("NFD", text)
    kept = "".join(c for c in decomposed if c not in _TONE_MARKS)
    return unicodedata.normalize("NFC", kept)


def split_syllables(pinyin: str, expect: int | None = None) -> list[str]:
    """Split pinyin into syllables, however it happens to be written.

    The curriculum stores both forms — 'lǐng qián' spaced and 'yóujú' joined, in
    roughly a 2:1 ratio — so neither can be assumed. Spacing is trusted when it
    is there; otherwise the toneless form is matched greedily, longest first,
    against the syllable inventory.

    `expect` is the number of Han characters, which is the number of syllables a
    Han word must have. A split that disagrees with it is wrong, so it is thrown
    away rather than shown.
    """
    pinyin = (pinyin or "").strip()
    if not pinyin:
        return []

    # Each whitespace-separated chunk is tokenised on its own, so a space is
    # always honoured as a boundary and never has to be one. The curriculum
    # spaces pinyin by syllable ('lǐng qián'), by word ('biànlì shāngdiàn' —
    # two chunks, four syllables), and not at all ('yóujú'), sometimes within
    # the same unit.
    out: list[str] = []
    for chunk in pinyin.split():
        piece = _split_chunk(chunk)
        if piece is None:
            return []
        out.extend(piece)

    if expect is not None and len(out) != expect:
        return []
    return out


def _split_chunk(chunk: str) -> list[str] | None:
    """Greedy longest-match over one whitespace-free run, or None if it can't."""
    plain = untone(chunk).lower()
    inventory = _syllables()
    out: list[str] = []
    i = 0
    while i < len(plain):
        for size in range(min(6, len(plain) - i), 0, -1):
            if plain[i : i + size] in inventory:
                out.append(chunk[i : i + size])
                i += size
                break
        else:
            return None
    return out


def syllable(pinyin: str) -> str:
    """One pinyin syllable as zhuyin, with the MOE neutral-tone placement."""
    from pypinyin.style.bopomofo import converter

    p = pinyin.strip().lower()
    # Erhua written as its own syllable (一會兒 "yī huì r"). pypinyin's 兒 rule
    # only fires on a tone-numbered "r5", so a bare "r" came out ㄖ — the
    # initial — instead of ㄦ, the final. It is the one entry in all 1,193
    # word-list readings that this got wrong.
    if p == "r":
        p = "er"
    out = converter.to_bopomofo(p)
    # MOE writes the neutral tone ahead of the syllable; pypinyin trails it.
    if out.endswith("˙"):
        out = "˙" + out[:-1]
    return out


def from_pinyin(pinyin: str, expect: int | None = None) -> str:
    """A word's pinyin as space-separated zhuyin, or '' when it cannot be split.

    Empty rather than wrong: a garbled reading printed beside a character teaches
    the learner something false, and a missing one only teaches them nothing.
    """
    parts = split_syllables(pinyin, expect)
    if not parts:
        return ""
    return " ".join(syllable(p) for p in parts if p)


_HAN = re.compile(r"[㐀-䶿一-鿿]")


def for_word(traditional: str, pinyin: str) -> str:
    """Zhuyin for a vocabulary entry, using its character count as the check."""
    return from_pinyin(pinyin, expect=len(_HAN.findall(traditional or "")) or None)
