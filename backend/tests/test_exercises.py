"""Tests for the lesson exercise-stream builder (spec §3.1)."""

from __future__ import annotations

from app import exercises

LESSON = {
    "id": "l_test",
    "title": "Test",
    "vocab": [
        {"id": "v_a", "traditional": "水", "pinyin": "shuǐ", "gloss": "water"},
        {"id": "v_b", "traditional": "便當", "pinyin": "biàndāng", "gloss": "boxed meal"},
        {"id": "v_c", "traditional": "杯", "pinyin": "bēi", "gloss": "cup"},
    ],
    "grammar": [
        {"id": "g_a", "title": "T", "pattern": "P", "explanation": "E", "examples": []},
    ],
    "dialogue": [{"speaker": "A", "hanzi": "你好", "pinyin": "nǐ hǎo", "gloss": "hi"}],
    "sentences": [
        {"tokens": ["我", "要", "水"], "pinyin": "wǒ yào shuǐ", "gloss": "I want water", "cloze_index": 2},
        {"tokens": ["一", "個", "便當"], "pinyin": "yí ge biàndāng", "gloss": "one boxed meal", "cloze_index": 2},
        {"tokens": ["一", "杯", "水"], "pinyin": "yì bēi shuǐ", "gloss": "a cup of water", "cloze_index": 1},
        {"tokens": ["我", "要", "杯"], "pinyin": "wǒ yào bēi", "gloss": "I want a cup", "cloze_index": 2},
    ],
}

POOL = LESSON["vocab"] + [
    {"id": "v_x", "traditional": "茶", "pinyin": "chá", "gloss": "tea"},
    {"id": "v_y", "traditional": "咖啡", "pinyin": "kāfēi", "gloss": "coffee"},
    {"id": "v_z", "traditional": "麵包", "pinyin": "miànbāo", "gloss": "bread"},
]


def test_stream_has_all_expected_kinds():
    stream = exercises.build_stream(LESSON, POOL)
    kinds = {e["kind"] for e in stream}
    assert "vocab_intro" in kinds
    assert "grammar" in kinds
    assert "match" in kinds
    assert "audio_meaning" in kinds
    assert "dialogue" in kinds
    # The sentence rotation yields cloze/tile_build/translate/listen_type.
    assert {"cloze", "tile_build", "translate", "listen_type"} <= kinds


def test_intro_card_per_vocab():
    stream = exercises.build_stream(LESSON, POOL)
    intros = [e for e in stream if e["kind"] == "vocab_intro"]
    assert len(intros) == len(LESSON["vocab"])


def test_deterministic_per_lesson():
    a = exercises.build_stream(LESSON, POOL)
    b = exercises.build_stream(LESSON, POOL)
    assert a == b  # same lesson -> identical stream (seeded RNG)


def test_gradable_flag_matches_kinds():
    stream = exercises.build_stream(LESSON, POOL)
    for e in stream:
        assert e["gradable"] == (e["kind"] in exercises.GRADABLE_KINDS)


def test_mc_options_have_exactly_one_correct():
    stream = exercises.build_stream(LESSON, POOL)
    for e in stream:
        opts = e["payload"].get("options")
        if opts:
            assert sum(1 for o in opts if o["correct"]) == 1
            assert len(opts) >= 2


def test_cloze_blanks_the_target_token():
    stream = exercises.build_stream(LESSON, POOL)
    clozes = [e for e in stream if e["kind"] == "cloze"]
    assert clozes, "expected at least one cloze exercise"
    for c in clozes:
        assert "＿＿" in c["payload"]["tokens"]
        correct = next(o["text"] for o in c["payload"]["options"] if o["correct"])
        # The correct answer is a real word, not the blank placeholder.
        assert correct != "＿＿"


def test_tile_build_tiles_are_a_permutation_of_answer():
    stream = exercises.build_stream(LESSON, POOL)
    for e in stream:
        if e["kind"] == "tile_build":
            assert sorted(e["payload"]["tiles"]) == sorted(e["payload"]["answer"])
