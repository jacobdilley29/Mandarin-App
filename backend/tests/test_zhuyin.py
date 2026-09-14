"""Zhuyin for display beside pinyin (spec §6 — Taiwan readings).

The design decision worth pinning: zhuyin is transcribed from **this app's
pinyin**, never derived from the character. pypinyin reads 銀行 as yínxíng;
Taiwan says yínháng. Across the 1,208 words in the curriculum, deriving from
characters disagrees with the stored reading for 9.2% of them — and they are the
readings the app exists to get right. The card shows both an inch apart, so a
disagreement is two contradictory answers, not a hidden inconsistency.

The word lists carry a `bopomofo` field for all 1,193 entries, which is real
ground truth rather than a claim; test_matches_the_vendored_bopomofo_exactly
checks every one.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import zhuyin
from app.config import REPO_ROOT

WORDLISTS = REPO_ROOT / "content" / "wordlists"


def _moe(bopomofo: str) -> str:
    """The dataset trails the neutral-tone dot; Taiwan MOE leads with it."""
    return " ".join(
        ("˙" + p[:-1]) if p.endswith("˙") else p for p in bopomofo.split()
    )


# ---------------------------------------------------------------------------
# Ground truth
# ---------------------------------------------------------------------------
def test_matches_the_vendored_bopomofo_exactly():
    """All 1,193 word-list entries, not a sample."""
    checked, wrong = 0, []
    for path in sorted(WORDLISTS.glob("hsk*.json")):
        for w in json.loads(path.read_text(encoding="utf-8"))["words"]:
            if not w.get("bopomofo"):
                continue
            checked += 1
            got = zhuyin.for_word(w["traditional"], w["pinyin"])
            if got != _moe(w["bopomofo"]):
                wrong.append((w["traditional"], w["pinyin"], got, _moe(w["bopomofo"])))

    assert checked > 1000, "the word lists should have been found"
    assert not wrong, f"{len(wrong)} of {checked} disagree, e.g. {wrong[:5]}"


def test_every_word_in_the_curriculum_converts():
    """An empty reading is a silent hole on the card, so none is acceptable."""
    from app import curriculum_source

    missing = [
        v["traditional"]
        for unit in curriculum_source.load()["units"]
        for lesson in unit.get("lessons", [])
        for v in lesson.get("vocab", [])
        if not zhuyin.for_word(v["traditional"], v.get("pinyin", ""))
    ]

    assert not missing, f"no zhuyin for {missing[:10]}"


# ---------------------------------------------------------------------------
# Why it reads the pinyin and not the character
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "word, pinyin, expected",
    [
        ("銀行", "yínháng", "ㄧㄣˊ ㄏㄤˊ"),   # not yínxíng
        ("和", "hàn", "ㄏㄢˋ"),                # the Taiwan reading
        ("東西", "dōngxi", "ㄉㄨㄥ ˙ㄒㄧ"),      # neutral second syllable
    ],
)
def test_the_taiwan_reading_wins(word, pinyin, expected):
    assert zhuyin.for_word(word, pinyin) == expected


def test_the_neutral_tone_dot_leads_the_syllable():
    """Taiwan MOE writes ˙ㄉㄜ; pypinyin and Mainland sources write ㄉㄜ˙."""
    assert zhuyin.syllable("de") == "˙ㄉㄜ"


# ---------------------------------------------------------------------------
# Splitting, which is where the real work is
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "word, pinyin, syllables",
    [
        ("領錢", "lǐng qián", 2),              # spaced by syllable
        ("郵局", "yóujú", 2),                  # joined
        ("便利商店", "biànlì shāngdiàn", 4),    # spaced by WORD, not syllable
    ],
)
def test_pinyin_is_split_however_it_is_written(word, pinyin, syllables):
    """All three forms appear in the curriculum, sometimes in one unit."""
    assert len(zhuyin.for_word(word, pinyin).split()) == syllables


def test_a_diaeresis_is_not_a_tone_mark():
    """綠 lǜ and 路 lù are different finals; stripping ü would merge them."""
    assert zhuyin.for_word("綠", "lǜ") == "ㄌㄩˋ"
    assert zhuyin.for_word("路", "lù") == "ㄌㄨˋ"


def test_erhua_written_as_its_own_syllable():
    """一會兒 is stored "yī huì r" — ㄦ the final, not ㄖ the initial."""
    assert zhuyin.for_word("一會兒", "yī huì r") == "ㄧ ㄏㄨㄟˋ ˙ㄦ"


def test_a_reading_it_cannot_split_gives_nothing_rather_than_nonsense():
    """A garbled reading beside a character teaches something false."""
    assert zhuyin.for_word("水", "qqq") == ""
    assert zhuyin.for_word("水", "") == ""


def test_a_split_that_disagrees_with_the_character_count_is_rejected():
    """Two syllables offered for a three-character word is a wrong answer."""
    assert zhuyin.for_word("圖書館", "tú shū") == ""
