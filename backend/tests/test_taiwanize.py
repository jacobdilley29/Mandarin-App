"""Taiwan-variant normalisation (spec §5 steps 2–3).

The app is Traditional-only Taiwan Guoyu, fed from mainland-standard sources.
Every one of these is a way that pipeline can quietly ship mainland Mandarin:
a simplified character leaking through, a PRC word taught as Taiwan usage, or a
reading that sends the wrong audio to TTS and the wrong target to tone training.
"""

from __future__ import annotations

import pytest

from app import taiwanize as tw


# ---------------------------------------------------------------------------
# 1. Characters — s2twp, not s2t
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "simplified, expected",
    [
        ("自行车", "腳踏車"),
        ("软件", "軟體"),
        ("信息", "資訊"),
        ("打印机", "印表機"),
        ("鼠标", "滑鼠"),
        ("方便面", "泡麵"),
    ],
)
def test_s2twp_substitutes_taiwan_vocabulary_not_just_characters(simplified, expected):
    """The whole reason the spec names s2twp over s2t."""
    assert tw.to_traditional_tw(simplified) == expected


def test_s2twp_does_strictly_more_than_s2t():
    import opencc

    s2t = opencc.OpenCC("s2t")
    # s2t only converts the characters; s2twp swaps the word.
    assert s2t.convert("自行车") == "自行車"
    assert tw.to_traditional_tw("自行车") == "腳踏車"


@pytest.mark.parametrize("text", ["腳踏車", "便利商店", "捷運", "手搖飲料", "悠遊卡"])
def test_taiwan_text_passes_through_unchanged(text):
    """Conversion must be safe to re-run over already-converted content."""
    assert tw.to_traditional_tw(text) == text


def test_empty_input_is_handled():
    assert tw.to_traditional_tw("") == ""


# ---------------------------------------------------------------------------
# 2. Vocabulary — the overrides cover what s2twp misses
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "prc, taiwan",
    [
        ("地鐵", "捷運"),
        ("公共汽車", "公車"),
        ("西紅柿", "番茄"),
        ("服務員", "服務生"),
        ("出租車", "計程車"),
        ("一會兒", "一下"),  # Taiwan avoids erhua
    ],
)
def test_override_table_substitutes_prc_words(prc, taiwan):
    entry, notes = tw.normalize_entry({"traditional": prc, "pinyin": "x"})
    assert entry["traditional"] == taiwan
    assert notes, "a substitution must be reported, not made silently"


def test_substitution_records_the_prc_form_and_a_note():
    """The learner should still be able to recognise the mainland word."""
    entry, _ = tw.normalize_entry({"traditional": "地鐵", "pinyin": "dìtiě"})
    assert entry["prc_form"] == "地鐵"
    assert entry["pinyin"] == "jiéyùn"
    assert "捷運" in entry["taiwan_note"]


def test_substitution_drops_stale_derived_fields():
    """bopomofo/readings described the word that was just replaced."""
    entry, _ = tw.normalize_entry(
        {"traditional": "地鐵", "pinyin": "dìtiě", "bopomofo": "ㄉㄧˋㄊㄧㄝˇ", "readings": ["dìtiě"]}
    )
    assert "bopomofo" not in entry and "readings" not in entry


def test_the_overrides_and_s2twp_do_not_disagree():
    """A word s2twp already handles must not also carry a conflicting override."""
    for prc, sub in tw.substitutions().items():
        converted = tw.to_traditional_tw(prc)
        if converted != prc:
            assert converted == sub["taiwan"], (
                f"s2twp maps {prc}->{converted} but the override says {sub['taiwan']}"
            )


# ---------------------------------------------------------------------------
# 3. Readings
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "word, reading",
    [
        ("垃圾", "lèsè"),     # not lājī
        ("企業", "qìyè"),     # not qǐyè
        ("星期", "xīngqí"),   # not xīngqī
        ("和", "hàn"),
        ("喜歡", "xǐhuān"),   # Taiwan keeps the full tone
        ("早上", "zǎoshàng"),
        ("晚上", "wǎnshàng"),
    ],
)
def test_pinned_taiwan_readings_win(word, reading):
    assert tw.pinyin_tw(word) == reading


def test_haochi_correction_is_applied():
    """好吃 'tasty' is hǎochī; hào chī means 'fond of eating' — wrong word entirely."""
    assert tw.pinyin_tw("好吃") == "hǎochī"


def test_pypinyin_generates_toned_pinyin_for_unpinned_words():
    assert tw.pinyin_tw("便利商店") == "biànlìshāngdiàn"
    assert tw.pinyin_tw("便利商店", spaced=True) == "biàn lì shāng diàn"


def test_readings_carry_tone_diacritics_not_numbers():
    """Style.TONE, per the spec — pinyin3 would be a different stack choice."""
    reading = tw.pinyin_tw("捷運")
    assert not any(c.isdigit() for c in reading)
    assert any(c in "āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ" for c in reading)


def test_sandhi_is_not_baked_into_stored_readings():
    """Base tones are stored; sandhi belongs to display and tone scoring."""
    assert tw.pinyin_tw("你好") == "nǐhǎo"  # not "níhǎo"


def test_apply_reading_reports_whether_it_changed_anything():
    pinned, changed = tw.apply_reading("垃圾", "lājī")
    assert (pinned, changed) == ("lèsè", True)

    same, changed = tw.apply_reading("垃圾", "lèsè")
    assert (same, changed) == ("lèsè", False)


def test_reading_comparison_ignores_spacing_and_unicode_form():
    import unicodedata

    assert tw.norm_pinyin("xǐ huān") == tw.norm_pinyin(
        unicodedata.normalize("NFD", "xǐhuān")
    )


# ---------------------------------------------------------------------------
# Canonical forms — a simplified character must never reach the learner
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("simplified, traditional", [("听", "聽"), ("几", "幾"), ("从", "從")])
def test_simplified_forms_are_pinned_to_traditional(simplified, traditional):
    assert tw.canonical_form(simplified) == traditional


def test_every_pin_that_s2twp_disagrees_with_is_explicitly_resolved():
    """A pin and s2twp wanting different words is an unmade editorial decision.

    Either the pinned form is right and s2twp is overruled, or s2twp is right and
    the word belongs in the substitution table. Both are fine; leaving it
    unreviewed is not, because whichever way it falls silently decides what
    Jacob is taught. This fails on any *new* divergence.

    Resolved so far: 联系 pinned to 聯繫, which s2twp maps to 聯絡 — Taiwan says
    聯絡 (聯絡方式, 保持聯絡), so it is now a substitution and s2twp wins.
    """
    for simplified, pinned in tw.canonical_forms().items():
        converted = tw.to_traditional_tw(pinned)
        if converted == pinned:
            continue
        assert pinned in tw.substitutions(), (
            f"{simplified} is pinned to {pinned} but s2twp wants {converted}, "
            f"and nothing in the substitution table settles which one is taught"
        )


def test_pins_survive_the_taiwan_standard_not_just_character_conversion():
    """群 is the Taiwan MOE standard; plain s2t prefers the variant 羣.

    A guard written against s2t rather than s2twp would 'fix' 群 into an archaic
    form — which is the whole reason the pin table exists on top of conversion.
    """
    assert tw.canonical_form("群") == "群"


def test_unpinned_words_fall_back_to_the_first_listed_form():
    assert tw.canonical_form("没有", ["沒有", "冇"]) == "沒有"
    assert tw.canonical_form("nothing-pinned", []) is None


# ---------------------------------------------------------------------------
# Review queue for readings no heuristic can settle
# ---------------------------------------------------------------------------
def test_polyphonic_words_are_flagged_for_review():
    flagged = tw.unresolved_readings([{"traditional": "了", "pinyin": "le", "readings": ["le", "liǎo"]}])
    assert flagged and "polyphonic" in flagged[0]["why"]


def test_mainland_neutral_tones_are_flagged():
    flagged = tw.unresolved_readings([{"traditional": "東西", "pinyin": "dōng xi"}])
    assert flagged and "mainland-neutral-tone" in flagged[0]["why"]


def test_genuinely_neutral_syllables_are_not_flagged():
    """了/的/嗎 are neutral in Taiwan too — flagging them would be noise."""
    assert tw.unresolved_readings([{"traditional": "好了", "pinyin": "hǎo le"}]) == []


def test_single_syllable_words_are_never_flagged_for_neutral_tone():
    assert tw.unresolved_readings([{"traditional": "書", "pinyin": "shū"}]) == []
