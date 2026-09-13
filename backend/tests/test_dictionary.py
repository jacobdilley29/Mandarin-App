"""Tap-to-define while reading (spec §5).

The point of contention is which source answers first. The app's own vocab
carries the Taiwan reading it taught — 銀行 yínháng, 和 hàn — and CC-CEDICT,
being Mainland-oriented, disagrees on precisely those words. Answering from
CC-CEDICT would show one reading in the lesson and another on tap, which is
worse than no lookup at all.

CC-CEDICT is also optional: it is a download that may never have been run, and
every test here passes with an empty dictionary table, because that is the state
a fresh install is in.
"""

from __future__ import annotations

import pytest

from app import dictionary

from .conftest import attached_conn


@pytest.fixture
def conn(tmp_path):
    c = attached_conn(tmp_path)
    c.executemany(
        """INSERT INTO vocab (id, traditional, pinyin, gloss, zhuyin)
           VALUES (?, ?, ?, ?, ?)""",
        [
            ("v_yh", "銀行", "yínháng", "bank", "ㄧㄣˊ ㄏㄤˊ"),
            ("v_wo", "我", "wǒ", "I; me", "ㄨㄛˇ"),
            ("v_yao", "要", "yào", "to want", "ㄧㄠˋ"),
            ("v_he", "喝", "hē", "to drink", "ㄏㄜ"),
            ("v_shui", "水", "shuǐ", "water", "ㄕㄨㄟˇ"),
            ("v_bl", "便利商店", "biànlì shāngdiàn", "convenience store", "ㄅㄧㄢˋ"),
        ],
    )
    c.commit()
    yield c
    c.close()


# ---------------------------------------------------------------------------
# Which source answers
# ---------------------------------------------------------------------------
def test_the_curriculum_answers_first(conn):
    """The reading on tap must be the reading the lesson taught."""
    entry = dictionary.lookup(conn, "銀行")

    assert entry["pinyin"] == "yínháng", "not CC-CEDICT's yínxíng"
    assert entry["source"] == "curriculum"
    assert entry["zhuyin"] == "ㄧㄣˊ ㄏㄤˊ"


def test_cedict_fills_the_gaps(conn):
    conn.execute(
        """INSERT INTO dictionary (traditional, pinyin, gloss)
           VALUES ('嚇', 'xia4', 'to frighten')"""
    )
    conn.commit()

    entry = dictionary.lookup(conn, "嚇")
    assert entry["gloss"] == "to frighten"
    assert entry["source"] == "cedict"


def test_a_taiwan_reading_in_cedict_wins_over_the_mainland_one(conn):
    conn.execute(
        """INSERT INTO dictionary (traditional, pinyin, pinyin_tw, gloss)
           VALUES ('垃圾', 'la1 ji1', 'lèsè', 'rubbish')"""
    )
    conn.commit()

    assert dictionary.lookup(conn, "垃圾")["pinyin"] == "lèsè"


def test_an_unknown_word_is_simply_unknown(conn):
    assert dictionary.lookup(conn, "沒有這個詞") is None


# ---------------------------------------------------------------------------
# Segmentation — what a tap actually selects
# ---------------------------------------------------------------------------
def test_a_sentence_splits_into_words_not_characters(conn):
    """我要喝水 is four characters and four words; 便利商店 is four and one."""
    spans = dictionary.annotate(conn, "我要喝水")

    assert [s["text"] for s in spans] == ["我", "要", "喝", "水"]
    assert all(s["entry"] for s in spans)


def test_the_longest_word_wins(conn):
    spans = dictionary.annotate(conn, "便利商店")

    assert [s["text"] for s in spans] == ["便利商店"]
    assert spans[0]["entry"]["gloss"] == "convenience store"


def test_punctuation_survives_unchanged(conn):
    spans = dictionary.annotate(conn, "我要喝水。")

    assert "".join(s["text"] for s in spans) == "我要喝水。"
    assert spans[-1]["entry"] is None and spans[-1]["plain"]


def test_an_undefined_character_still_renders(conn):
    """The sentence must read identically whether or not a lookup exists."""
    spans = dictionary.annotate(conn, "我嚇你")

    assert "".join(s["text"] for s in spans) == "我嚇你"
    assert [s["text"] for s in spans if s["entry"] is None] == ["嚇", "你"]


def test_it_works_with_no_dictionary_table_at_all(conn):
    """A fresh install has never run the CC-CEDICT import."""
    conn.execute("DROP TABLE dictionary")
    conn.commit()

    spans = dictionary.annotate(conn, "我要喝水")

    assert [s["text"] for s in spans] == ["我", "要", "喝", "水"]
    assert dictionary.lookup(conn, "沒") is None


def test_latin_and_digits_pass_through(conn):
    spans = dictionary.annotate(conn, "MRT 3 號")

    assert "".join(s["text"] for s in spans) == "MRT 3 號"
