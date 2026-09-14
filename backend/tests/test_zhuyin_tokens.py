"""Per-token readings: one reading per tile, derived from the sentence's pinyin.

A tile shows a word and the reading under it. The content stores neither — a
sentence carries a `tokens` list and one pinyin string for the whole sentence —
so the reading has to be split out and handed back to the right token.

The rule these tests exist to pin down is the one `zhuyin.py` already states for
whole words: **empty rather than wrong**. A tile labelled with the wrong reading
teaches the learner something false and does it at the exact moment they are
paying attention to it.
"""

from __future__ import annotations

from app import zhuyin


def texts(rows: list[dict]) -> list[str]:
    return [r["text"] for r in rows]


def readings(rows: list[dict]) -> list[str | None]:
    return [r["pinyin"] for r in rows]


def test_splits_a_spaced_sentence_by_token():
    rows = zhuyin.for_tokens(["我", "要", "一", "個", "便當"], "Wǒ yào yí ge biàndāng.")
    assert texts(rows) == ["我", "要", "一", "個", "便當"]
    assert readings(rows) == ["Wǒ", "yào", "yí", "ge", "biàndāng"]


def test_multi_character_token_keeps_its_syllables_together():
    rows = zhuyin.for_tokens(["那", "是", "便利商店"], "Nà shì biànlì shāngdiàn.")
    assert readings(rows) == ["Nà", "shì", "biànlì shāngdiàn"]
    # Four characters, four zhuyin syllables, in one tile.
    assert len(rows[2]["zhuyin"].split()) == 4


def test_trailing_punctuation_does_not_break_the_split():
    """`_split_chunk` matches alpha runs, so a bare '.' or '?' fails the whole
    sentence unless it is stripped first. Every dialogue line ends in one."""
    for sentence in ("Nǐ hǎo.", "Nǐ hǎo?", "Nǐ hǎo!", "Nǐ hǎo，"):
        rows = zhuyin.for_tokens(["你", "好"], sentence)
        assert readings(rows) == ["Nǐ", "hǎo"], sentence


def test_internal_punctuation_does_not_break_the_split():
    rows = zhuyin.for_tokens(
        ["不好意思", "，", "請問"], "Bùhǎoyìsi, qǐngwèn?"
    )
    assert texts(rows) == ["不好意思", "，", "請問"]
    assert readings(rows) == ["Bùhǎoyìsi", None, "qǐngwèn"]


def test_zhuyin_uses_the_moe_neutral_tone_placement():
    rows = zhuyin.for_tokens(["東西"], "dōngxi")
    assert rows[0]["zhuyin"] == "ㄉㄨㄥ ˙ㄒㄧ"


def test_erhua_written_as_its_own_syllable():
    rows = zhuyin.for_tokens(["一會兒"], "yī huì r")
    assert rows[0]["zhuyin"] == "ㄧ ㄏㄨㄟˋ ˙ㄦ"


def test_syllable_count_mismatch_yields_no_readings_at_all():
    """Two syllables offered for three characters. Handing back a partial
    mapping would put 好's reading under 嗎."""
    rows = zhuyin.for_tokens(["你", "好", "嗎"], "Nǐ hǎo")
    assert texts(rows) == ["你", "好", "嗎"]
    assert readings(rows) == [None, None, None]


def test_unsplittable_pinyin_yields_no_readings():
    rows = zhuyin.for_tokens(["你", "好"], "qqq zzz")
    assert readings(rows) == [None, None]


def test_missing_pinyin_is_not_an_error():
    rows = zhuyin.for_tokens(["你", "好"], "")
    assert texts(rows) == ["你", "好"]
    assert readings(rows) == [None, None]


def test_no_tokens_is_not_an_error():
    assert zhuyin.for_tokens([], "Nǐ hǎo") == []


def test_every_row_carries_all_three_keys():
    """The frontend destructures these; a missing key is a silent undefined."""
    for rows in (
        zhuyin.for_tokens(["你", "好"], "Nǐ hǎo"),
        zhuyin.for_tokens(["你", "好"], "broken"),
    ):
        for row in rows:
            assert set(row) == {"text", "pinyin", "zhuyin"}


def test_a_word_reading_matches_for_word():
    """for_tokens on a single token must agree with the existing whole-word
    transcription — two ways of asking the same question."""
    rows = zhuyin.for_tokens(["便利商店"], "biànlì shāngdiàn")
    assert rows[0]["zhuyin"] == zhuyin.for_word("便利商店", "biànlì shāngdiàn")


# --- The greedy-split bug these readings uncovered -------------------------
#
# Several syllables are prefixes of a longer non-syllable, so a greedy splitter
# walks into a dead end on a word it can perfectly well split. These three
# carried no zhuyin at all until _split_chunk learned to backtrack — not a
# per-token problem, a whole-word one that per-token readings made visible.


def test_a_syllable_that_is_a_prefix_of_a_dead_end_still_splits():
    assert zhuyin.split_syllables("nánguò") == ["nán", "guò"]   # not nang + uo
    assert zhuyin.split_syllables("Qùnián") == ["Qù", "nián"]   # not qun + ian
    assert zhuyin.split_syllables("fànguǎn") == ["fàn", "guǎn"]  # not fang + uan


def test_those_words_now_carry_zhuyin():
    assert zhuyin.for_word("難過", "nánguò") == "ㄋㄢˊ ㄍㄨㄛˋ"
    assert zhuyin.for_word("去年", "qùnián") == "ㄑㄩˋ ㄋㄧㄢˊ"
    assert zhuyin.for_word("飯館", "fànguǎn") == "ㄈㄢˋ ㄍㄨㄢˇ"


def test_longest_match_is_still_preferred():
    """Backtracking must not turn a real one-syllable chunk into two."""
    assert zhuyin.split_syllables("xiàng") == ["xiàng"]
    assert zhuyin.split_syllables("zhuāng") == ["zhuāng"]


def test_interjection_syllables_do_not_hijack_a_word():
    """pypinyin's inventory contains bare 'o' and 'ng', so 'bàngōngshì' has a
    legal four-syllable reading (bàng·ō·ng·shì) for a three-character word.
    Fewest-syllables picks the one that is actually the word."""
    assert zhuyin.split_syllables("bàngōngshì") == ["bàn", "gōng", "shì"]
    assert zhuyin.for_word("辦公室", "bàngōngshì") == "ㄅㄢˋ ㄍㄨㄥ ㄕˋ"
