"""Tests for pinyin → zhuyin conversion (Taiwan phonetic notation)."""

from __future__ import annotations

import json
from pathlib import Path

from app import zhuyin
from app.config import REPO_ROOT


def test_basic_words():
    assert zhuyin.to_zhuyin("biànlì", "便利") == "ㄅㄧㄢˋ ㄌㄧˋ"
    assert zhuyin.to_zhuyin("shāngdiàn", "商店") == "ㄕㄤ ㄉㄧㄢˋ"
    assert zhuyin.to_zhuyin("lǎoshī", "老師") == "ㄌㄠˇ ㄕ"


def test_all_four_tones_and_neutral():
    assert zhuyin.to_zhuyin("mā", "媽") == "ㄇㄚ"
    assert zhuyin.to_zhuyin("má", "麻") == "ㄇㄚˊ"
    assert zhuyin.to_zhuyin("mǎ", "馬") == "ㄇㄚˇ"
    assert zhuyin.to_zhuyin("mà", "罵") == "ㄇㄚˋ"
    # Neutral tone takes a leading dot, not a trailing mark.
    assert zhuyin.to_zhuyin("xièxie", "謝謝") == "ㄒㄧㄝˋ ˙ㄒㄧㄝ"


def test_empty_final_after_retroflex_and_sibilant():
    # The "i" in zhi/chi/shi/ri/zi/ci/si is not a vowel — no ㄧ may appear.
    for pinyin, hanzi, expected in [
        ("zhī", "之", "ㄓ"), ("chī", "吃", "ㄔ"), ("shì", "是", "ㄕˋ"),
        ("rì", "日", "ㄖˋ"), ("zì", "字", "ㄗˋ"), ("cì", "次", "ㄘˋ"),
        ("sì", "四", "ㄙˋ"),
    ]:
        assert zhuyin.to_zhuyin(pinyin, hanzi) == expected


def test_abbreviated_finals_are_expanded():
    # -iu is really -iou, -ui is -uei, -un is -uen, -ong is ㄨㄥ.
    assert zhuyin.to_zhuyin("jiǔ", "九") == "ㄐㄧㄡˇ"
    assert zhuyin.to_zhuyin("huì", "會") == "ㄏㄨㄟˋ"
    assert zhuyin.to_zhuyin("lùn", "論") == "ㄌㄨㄣˋ"
    assert zhuyin.to_zhuyin("dōng", "東") == "ㄉㄨㄥ"
    assert zhuyin.to_zhuyin("xiōng", "兄") == "ㄒㄩㄥ"


def test_u_after_jqx_is_really_yu():
    assert zhuyin.to_zhuyin("qù", "去") == "ㄑㄩˋ"
    assert zhuyin.to_zhuyin("xué", "學") == "ㄒㄩㄝˊ"
    assert zhuyin.to_zhuyin("juǎn", "捲") == "ㄐㄩㄢˇ"
    assert zhuyin.to_zhuyin("qún", "群") == "ㄑㄩㄣˊ"
    # ...but after n/l the umlaut is written, and must survive.
    assert zhuyin.to_zhuyin("nǚ", "女") == "ㄋㄩˇ"
    assert zhuyin.to_zhuyin("lǜ", "綠") == "ㄌㄩˋ"


def test_zero_initial_respellings():
    assert zhuyin.to_zhuyin("yī", "一") == "ㄧ"
    assert zhuyin.to_zhuyin("wǒ", "我") == "ㄨㄛˇ"
    assert zhuyin.to_zhuyin("yòng", "用") == "ㄩㄥˋ"  # yong is ㄩㄥ, not ㄧㄥ
    assert zhuyin.to_zhuyin("yǒu", "有") == "ㄧㄡˇ"
    assert zhuyin.to_zhuyin("wèi", "位") == "ㄨㄟˋ"
    assert zhuyin.to_zhuyin("yuǎn", "遠") == "ㄩㄢˇ"
    assert zhuyin.to_zhuyin("ér", "兒") == "ㄦˊ"


def test_hanzi_resolves_segmentation_ambiguity():
    # "xian" can be read xian (1 syllable) or xi-an (2). The characters decide.
    assert zhuyin.to_zhuyin("xiān", "先") == "ㄒㄧㄢ"
    assert zhuyin.to_zhuyin("xīān", "西安") == "ㄒㄧ ㄢ"


def test_word_grouped_pinyin_is_segmented():
    # Content pinyin has no space between syllables of a word (see tones.py).
    assert zhuyin.to_zhuyin("biàndāng", "便當") == "ㄅㄧㄢˋ ㄉㄤ"
    assert zhuyin.to_zhuyin("jiǎotàchē", "腳踏車") == "ㄐㄧㄠˇ ㄊㄚˋ ㄔㄜ"


def test_sentence_keeps_punctuation():
    assert zhuyin.to_zhuyin("Tā shì lǎoshī。", "他是老師。") == "ㄊㄚ ㄕˋ ㄌㄠˇ ㄕ。"


def test_numeric_tones_supported():
    assert zhuyin.to_zhuyin("bian4li4", "便利") == "ㄅㄧㄢˋ ㄌㄧˋ"


def test_returns_none_rather_than_guessing():
    # Count mismatch against the characters.
    assert zhuyin.to_zhuyin("biànlì", "便") is None
    # Not pinyin at all.
    assert zhuyin.to_zhuyin("qqq", "哈") is None
    assert zhuyin.to_zhuyin("", "我") is None
    assert zhuyin.to_zhuyin("hello world", "你好") is None


def test_every_shipped_content_string_converts():
    """The whole committed curriculum must convert — no silent pinyin fallback."""
    failures: list[tuple[str, str]] = []

    def check(pinyin: str | None, hanzi: str | None) -> None:
        if pinyin and hanzi and zhuyin.to_zhuyin(pinyin, hanzi) is None:
            failures.append((hanzi, pinyin))

    def check_vocab(v: dict) -> None:
        check(v.get("pinyin"), v.get("traditional"))
        ex = v.get("example") or {}
        check(ex.get("pinyin"), ex.get("hanzi"))

    content = REPO_ROOT / "content"
    for name in ("curriculum.json", "hsk1.json"):
        data = json.loads(Path(content / name).read_text(encoding="utf-8"))
        for v in data.get("vocab", []):
            check_vocab(v)
        for unit in data.get("units", []):
            for lesson in unit.get("lessons", []):
                for v in lesson.get("vocab", []):
                    check_vocab(v)
                for g in lesson.get("grammar", []):
                    for ex in g.get("examples", []):
                        check(ex.get("pinyin"), ex.get("hanzi"))
                for s in lesson.get("sentences", []):
                    check(s.get("pinyin"), "".join(s.get("tokens", [])))
                for line in lesson.get("dialogue", []):
                    check(line.get("pinyin"), line.get("hanzi"))

    assert not failures, f"{len(failures)} string(s) failed to convert: {failures[:10]}"
