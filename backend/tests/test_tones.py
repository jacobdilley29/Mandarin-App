"""Tests for tone extraction (spec §3.3 tone ear-training)."""

from __future__ import annotations

from app import tones


def test_tone_of_syllable_all_tones():
    assert tones.tone_of_syllable("mā") == 1
    assert tones.tone_of_syllable("má") == 2
    assert tones.tone_of_syllable("mǎ") == 3
    assert tones.tone_of_syllable("mà") == 4
    assert tones.tone_of_syllable("ma") == 5  # neutral / unmarked


def test_tones_from_word_grouped_pinyin():
    # Multi-syllable tokens with no internal space must still yield one tone each.
    assert tones.tones_from_pinyin("biàndāng") == [4, 1]
    assert tones.tones_from_pinyin("biànlì shāngdiàn") == [4, 4, 1, 4]
    assert tones.tones_from_pinyin("péngyǒu") == [2, 3]


def test_han_syllable_count():
    assert tones.han_syllable_count("水") == 1
    assert tones.han_syllable_count("便當") == 2
    assert tones.han_syllable_count("便利商店") == 4
    assert tones.han_syllable_count("") == 0


def test_numeric_pinyin_supported():
    assert tones.tones_from_pinyin("bian4dang1") == [4, 1]


def test_tone_pairs_are_sixteen_core_combos():
    pairs = tones.tone_pairs()
    assert len(pairs) == 16
    assert (3, 3) in pairs and (2, 4) in pairs
