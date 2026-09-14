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


def _only(stream, kind):
    return [e["payload"] for e in stream if e["kind"] == kind]


def test_tile_build_tiles_are_a_permutation_of_answer():
    stream = exercises.build_stream(LESSON, POOL)
    for p in _only(stream, "tile_build"):
        assert sorted(t["text"] for t in p["tiles"]) == sorted(p["answer"])


def test_every_tile_carries_its_own_reading():
    """A tile shows a word with pinyin or 注音 under it, per the Me-tab setting.
    The reading has to be on the tile itself — the sentence-level pinyin cannot
    be sliced up in the browser."""
    stream = exercises.build_stream(LESSON, POOL)
    tiles = [t for p in _only(stream, "tile_build") for t in p["tiles"]]
    assert tiles
    for t in tiles:
        assert set(t) == {"text", "pinyin", "zhuyin"}
        assert t["pinyin"], t
        assert t["zhuyin"], t


def test_a_tile_whose_reading_cannot_be_derived_still_renders():
    """Unsplittable pinyin loses the readings, never the drill."""
    lesson = {**LESSON, "sentences": [
        {"tokens": ["我", "要", "水"], "pinyin": "???", "gloss": "g", "cloze_index": 2},
    ]}
    for p in _only(exercises.build_stream(lesson, POOL), "tile_build"):
        assert [t["text"] for t in p["tiles"]]
        assert all(t["pinyin"] is None and t["zhuyin"] is None for t in p["tiles"])


# ---------------------------------------------------------------------------
# Dictation by tiles (was: type what you hear)
# ---------------------------------------------------------------------------
def test_listen_type_offers_tiles_rather_than_a_text_box():
    stream = exercises.build_stream(LESSON, POOL)
    payloads = _only(stream, "listen_type")
    assert payloads
    for p in payloads:
        assert p["tiles"], "dictation is built from tiles, not typed"
        assert set(p["tiles"][0]) == {"text", "pinyin", "zhuyin"}
        # The answer is still the sentence, token by token.
        assert "".join(p["answer"]) == p["audio_text"]


def test_dictation_tiles_include_decoys():
    """Without decoys the drill is a word-order puzzle: every tile belongs in
    the answer, so the learner never has to recognise a character."""
    stream = exercises.build_stream(LESSON, POOL)
    for p in _only(stream, "listen_type"):
        texts = [t["text"] for t in p["tiles"]]
        extra = sorted(_multiset_difference(texts, p["answer"]))
        assert extra, "no decoy tiles"
        assert not set(extra) & set(p["answer"])


def test_dictation_answer_is_still_buildable_from_the_tiles():
    """Every token of the answer must actually be on the rack, counting
    repeats — 我要水/我要杯 share tokens, and a missing duplicate makes the
    exercise unsolvable."""
    stream = exercises.build_stream(LESSON, POOL)
    for p in _only(stream, "listen_type"):
        assert not _multiset_difference(p["answer"], [t["text"] for t in p["tiles"]])


def _multiset_difference(a: list[str], b: list[str]) -> list[str]:
    rest = list(b)
    out = []
    for x in a:
        if x in rest:
            rest.remove(x)
        else:
            out.append(x)
    return out


# ---------------------------------------------------------------------------
# Character recognition (spec §3.2)
# ---------------------------------------------------------------------------
def _stream_for(vocab, pool=None):
    from app import exercises

    lesson = {
        "id": "l_t", "title": "T",
        "vocab": vocab, "grammar": [], "sentences": [], "dialogue": [],
    }
    return exercises.build_stream(lesson, pool or vocab)


def test_character_recognition_is_generated_for_every_word():
    from app import exercises

    vocab = [
        {"id": "v1", "traditional": "甜度", "pinyin": "tiándù", "gloss": "sweetness"},
        {"id": "v2", "traditional": "冰塊", "pinyin": "bīngkuài", "gloss": "ice"},
    ]
    stream = _stream_for(vocab)
    items = [e for e in stream if e["kind"] == "char_recognition"]

    assert len(items) == len(vocab)
    assert "char_recognition" in exercises.GRADABLE_KINDS


def test_character_recognition_gives_meaning_and_sound_but_not_the_characters():
    """Every other drill shows the characters; this one asks for them."""
    vocab = [{"id": "v1", "traditional": "甜度", "pinyin": "tiándù", "gloss": "sweetness"}]
    p = [e for e in _stream_for(vocab) if e["kind"] == "char_recognition"][0]["payload"]

    assert p["gloss"] == "sweetness" and p["pinyin"] == "tiándù"
    assert p["answer"] == "甜度"
    assert sum(1 for o in p["options"] if o["correct"]) == 1


def test_distractors_are_confusable_not_random():
    """Random options make this a test of nothing — the answer stands out at a glance."""
    from app import exercises

    rng = __import__("random").Random(0)
    pool = [
        {"id": "a", "traditional": "溫度"}, {"id": "b", "traditional": "態度"},
        {"id": "c", "traditional": "甜"},   {"id": "d", "traditional": "電視"},
        {"id": "e", "traditional": "腳踏車"},
    ]
    picked = exercises._confusable_words(pool, "甜度", 3, rng)

    # Words sharing a character come first: 溫度/態度 share 度, 甜 shares 甜.
    assert set(picked) <= {"溫度", "態度", "甜", "電視"}
    assert "腳踏車" not in picked, "a 3-character word is not confusable with a 2-character one"


def test_confusable_distractors_never_include_the_answer():
    from app import exercises

    rng = __import__("random").Random(0)
    pool = [{"id": "a", "traditional": "甜度"}, {"id": "b", "traditional": "溫度"}]
    assert "甜度" not in exercises._confusable_words(pool, "甜度", 3, rng)


def test_a_tiny_pool_still_produces_options():
    from app import exercises

    rng = __import__("random").Random(0)
    picked = exercises._confusable_words([{"id": "a", "traditional": "水"}], "茶", 3, rng)
    assert picked == ["水"]


# ---------------------------------------------------------------------------
# Gloss trimming — dictionary entries are not answer buttons
# ---------------------------------------------------------------------------
def test_long_dictionary_glosses_are_trimmed():
    from app.exercises import short_gloss

    raw = ("to have; there is; (bound form) having; with; -ful; -ed; -al "
           "(as in 意 intentional)")
    out = short_gloss(raw)

    assert len(out) <= 50
    assert out.startswith("to have")


def test_short_glosses_are_left_alone():
    from app.exercises import short_gloss

    assert short_gloss("water") == "water"
    assert short_gloss("boxed meal; bento") == "boxed meal; bento"


def test_empty_gloss_is_handled():
    from app.exercises import short_gloss

    assert short_gloss(None) == "" and short_gloss("") == ""


def test_distractor_glosses_are_trimmed_too():
    """If only the correct answer is short, length alone gives it away."""
    from app import exercises

    rng = __import__("random").Random(0)
    pool = [
        {"id": "a", "gloss": "x; " * 40},
        {"id": "b", "gloss": "y; " * 40},
        {"id": "c", "gloss": "z; " * 40},
        {"id": "target", "gloss": "water"},
    ]
    for g in exercises._distractor_glosses(pool, "target", 3, rng):
        assert len(g) <= 50
