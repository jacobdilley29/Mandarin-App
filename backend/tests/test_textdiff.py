"""Tests for dictation diffing (spec §7: pinyin/character diffing)."""

from __future__ import annotations

from app import textdiff


def _types(result):
    return [s["type"] for s in result["segments"]]


def test_han_exact_match():
    r = textdiff.han_diff("我要一個便當", "我要一個便當")
    assert r["correct"]
    assert _types(r) == ["equal"]


def test_han_ignores_punctuation_and_spaces():
    r = textdiff.han_diff("我要水。", " 我要水 ")
    assert r["correct"]


def test_han_missing_character():
    r = textdiff.han_diff("我要一個便當", "我要一個便")
    assert not r["correct"]
    assert "missing" in _types(r)
    missing = next(s for s in r["segments"] if s["type"] == "missing")
    assert missing["text"] == "當"


def test_han_substitution():
    r = textdiff.han_diff("我要茶", "我要水")
    assert not r["correct"]
    wrong = next(s for s in r["segments"] if s["type"] == "wrong")
    assert wrong["expected"] == "茶" and wrong["got"] == "水"


def test_han_extra_character():
    r = textdiff.han_diff("我要水", "我要水嗎")
    assert not r["correct"]
    assert "extra" in _types(r)


def test_pinyin_tone_sensitive_vs_insensitive():
    # Same syllables, wrong tone.
    strict = textdiff.pinyin_diff("wǒ yào shuǐ", "wo yao shui", tone_sensitive=True)
    loose = textdiff.pinyin_diff("wǒ yào shuǐ", "wo yao shui", tone_sensitive=False)
    assert not strict["correct"]
    assert loose["correct"]


def test_pinyin_syllable_missing():
    r = textdiff.pinyin_diff("wǒ yào shuǐ", "wǒ yào", tone_sensitive=True)
    assert not r["correct"]
    assert "missing" in _types(r)


def test_strip_tones():
    assert textdiff.strip_tones("biàndāng") == "biandang"
    assert textdiff.strip_tones("lǜsè") == "lvse"


def test_syllables_splitting():
    assert textdiff.syllables("Wǒ yào shuǐ.") == ["wǒ", "yào", "shuǐ"]
    assert textdiff.syllables("Wǒ yào shuǐ.", tone_sensitive=False) == ["wo", "yao", "shui"]


def test_dictation_check_auto_selects_mode():
    han = textdiff.dictation_check("我要水", "wǒ yào shuǐ", "我要水")
    assert han["mode"] == "han" and han["correct"]
    py = textdiff.dictation_check("我要水", "wǒ yào shuǐ", "wǒ yào shuǐ")
    assert py["mode"] == "pinyin" and py["correct"]
