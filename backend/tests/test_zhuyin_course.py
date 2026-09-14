"""The 注音 mini-course: the alphabet itself, taught rather than displayed.

The app prints zhuyin beside every word already. This is the course that makes
that useful to someone who cannot read it yet — the 37 symbols, the order they
are recited in, and what each one sounds like.

Two things here are load-bearing and easy to get quietly wrong:

* **The content file has to be self-consistent with the transcriber.** Each
  symbol carries a Han character that voices it, because text-to-speech cannot
  pronounce a bare ㄅ. If that character's reading does not actually contain the
  symbol it is teaching, the course plays the wrong sound with a straight face.
* **Symbols are SRS items like any other.** They go in the same queue as vocab
  and grammar, which means `review.build_queue` has to know how to render one.
"""

from __future__ import annotations

import json

import pytest

from app import review, srs, zhuyin, zhuyin_course

from .conftest import attached_conn


@pytest.fixture
def db(tmp_path):
    c = attached_conn(tmp_path)
    yield c
    c.close()


# ---------------------------------------------------------------------------
# The content file
# ---------------------------------------------------------------------------
def test_the_alphabet_is_complete():
    """21 initials, 3 medials, 13 finals — the 37 of 注音符號 — and the four
    tone marks. The first tone is unmarked, so there is no symbol for it."""
    groups: dict[str, int] = {}
    for s in zhuyin_course.symbols():
        groups[s["group"]] = groups.get(s["group"], 0) + 1
    assert groups == {"initial": 21, "medial": 3, "final": 13, "tone": 4}


def test_symbols_are_distinct_and_ordered():
    syms = zhuyin_course.symbols()
    assert len({s["symbol"] for s in syms}) == len(syms)
    assert [s["order"] for s in syms] == list(range(1, len(syms) + 1))


def test_recitation_order_starts_the_way_taiwan_recites_it():
    assert [s["symbol"] for s in zhuyin_course.symbols()][:4] == ["ㄅ", "ㄆ", "ㄇ", "ㄈ"]


def test_every_symbol_has_a_voice_and_an_example():
    for s in zhuyin_course.symbols():
        assert s["voice"] and s["voice_pinyin"], s["symbol"]
        assert s["example"]["traditional"] and s["example"]["pinyin"], s["symbol"]


def test_each_voicing_actually_contains_the_symbol_it_teaches():
    """The check that makes the audio trustworthy: transcribe the teaching
    syllable with our own converter and the symbol must be in it. ㄅ voiced by
    波 bō gives ㄅㄛ — ㄅ is there. A typo in the file fails here rather than
    playing the wrong sound to the learner."""
    for s in zhuyin_course.symbols():
        if s["group"] == "tone":
            continue
        transcribed = zhuyin.for_word(s["voice"], s["voice_pinyin"])
        assert s["symbol"] in transcribed, (s["symbol"], s["voice"], transcribed)


def test_every_symbol_is_taught_by_exactly_one_lesson():
    taught = [sym for les in zhuyin_course.lessons() for sym in les["symbols"]]
    assert sorted(taught) == sorted(s["symbol"] for s in zhuyin_course.symbols())


def test_lessons_follow_the_recitation_order():
    """A course that teaches ㄍ before ㄅ would be teaching a different order
    from the one the learner needs to recite."""
    order = {s["symbol"]: s["order"] for s in zhuyin_course.symbols()}
    taught = [order[sym] for les in zhuyin_course.lessons() for sym in les["symbols"]]
    assert taught == sorted(taught)


# ---------------------------------------------------------------------------
# The exercise stream
# ---------------------------------------------------------------------------
def test_a_lesson_builds_a_stream_with_every_drill_kind():
    stream = zhuyin_course.build_stream(zhuyin_course.lessons()[0])
    kinds = {e["kind"] for e in stream}
    assert "zhuyin_intro" in kinds
    assert {"zhuyin_sound", "zhuyin_symbol", "zhuyin_order"} <= kinds


def test_every_symbol_in_the_lesson_gets_an_intro_card():
    lesson = zhuyin_course.lessons()[0]
    stream = zhuyin_course.build_stream(lesson)
    intros = [e["payload"]["symbol"] for e in stream if e["kind"] == "zhuyin_intro"]
    assert intros == lesson["symbols"]


def test_drills_carry_the_symbol_they_are_about():
    """The SRS card is keyed on it; a drill with no symbol is unscoreable."""
    stream = zhuyin_course.build_stream(zhuyin_course.lessons()[0])
    for e in stream:
        if e["gradable"]:
            assert e["payload"].get("symbol") in {s["symbol"] for s in zhuyin_course.symbols()}


def test_audio_plays_a_han_character_never_a_bare_symbol():
    """edge-tts reads Han. Handing it ㄅ produces silence or nonsense."""
    stream = zhuyin_course.build_stream(zhuyin_course.lessons()[0])
    for e in stream:
        audio = e["payload"].get("audio_text")
        if audio:
            assert not any(c in audio for c in "ㄅㄆㄇㄈㄉㄊㄋㄌ"), e["kind"]


def test_the_sound_drill_offers_distractors_from_the_same_lesson():
    """Distinguishing ㄅ from ㄍ is not the lesson; distinguishing it from ㄆ
    is — they are all made at the lips and differ by a puff of air. Options
    pulled from elsewhere in the alphabet make the drill free, which the first
    version of this did, and a weaker assertion here let it through."""
    for lesson in zhuyin_course.lessons():
        siblings = set(lesson["symbols"])
        if len(siblings) < 4:
            continue  # smaller lessons must borrow; see the next test
        for e in zhuyin_course.build_stream(lesson):
            if e["kind"] != "zhuyin_sound":
                continue
            texts = {o["text"] for o in e["payload"]["options"]}
            assert texts <= siblings, (lesson["id"], texts - siblings)
            assert sum(1 for o in e["payload"]["options"] if o["correct"]) == 1


def test_a_small_lesson_borrows_distractors_rather_than_offering_fewer():
    """ㄍㄎㄏ is three symbols; a four-option drill has to reach outside it.
    Three options would make every drill in that lesson easier than the rest."""
    lesson = next(les for les in zhuyin_course.lessons() if len(les["symbols"]) == 3)
    for e in zhuyin_course.build_stream(lesson):
        if e["kind"] == "zhuyin_sound":
            assert len(e["payload"]["options"]) == zhuyin_course.OPTIONS


def test_review_distractors_are_the_symbols_lesson_too():
    """A card in the daily queue has no lesson in hand, so it has to find the
    one that teaches its symbol — otherwise reviews get easier than lessons."""
    card = {"item_id": "ㄅ", "reps": 0}
    rendered = zhuyin_course.render_card(card)
    assert {o["text"] for o in rendered["options"]} <= {"ㄅ", "ㄆ", "ㄇ", "ㄈ"}


def test_the_order_drill_is_a_shuffle_of_the_lesson():
    for e in zhuyin_course.build_stream(zhuyin_course.lessons()[0]):
        if e["kind"] == "zhuyin_order":
            p = e["payload"]
            assert sorted(t["text"] for t in p["tiles"]) == sorted(p["answer"])
            assert len(p["answer"]) >= 3


def test_an_unknown_lesson_is_not_a_crash(db):
    assert zhuyin_course.get_lesson(db, "nope") is None


# ---------------------------------------------------------------------------
# Progress and the SRS
# ---------------------------------------------------------------------------
def test_the_course_lists_its_lessons_with_progress(db):
    course = zhuyin_course.course(db)
    assert len(course["lessons"]) == len(zhuyin_course.lessons())
    first = course["lessons"][0]
    assert first["unlocked"] is True, "the first lesson is always open"
    assert first["completed"] is False
    assert course["lessons"][1]["unlocked"] is False


def test_passing_a_lesson_unlocks_the_next_and_seeds_cards(db):
    lesson = zhuyin_course.lessons()[0]
    results = [{"symbol": s, "correct": True} for s in lesson["symbols"]]
    out = zhuyin_course.record(db, lesson["id"], results)

    assert out["passed"] is True
    assert out["new_srs_cards"] == len(lesson["symbols"])

    course = zhuyin_course.course(db)
    assert course["lessons"][0]["completed"] is True
    assert course["lessons"][1]["unlocked"] is True


def test_failing_a_lesson_seeds_nothing(db):
    lesson = zhuyin_course.lessons()[0]
    results = [{"symbol": s, "correct": False} for s in lesson["symbols"]]
    out = zhuyin_course.record(db, lesson["id"], results)
    assert out["passed"] is False
    assert out["new_srs_cards"] == 0
    assert zhuyin_course.course(db)["lessons"][1]["unlocked"] is False


def test_a_second_pass_does_not_duplicate_cards(db):
    lesson = zhuyin_course.lessons()[0]
    results = [{"symbol": s, "correct": True} for s in lesson["symbols"]]
    zhuyin_course.record(db, lesson["id"], results)
    again = zhuyin_course.record(db, lesson["id"], results)
    assert again["new_srs_cards"] == 0

    n = db.execute(
        "SELECT COUNT(*) AS n FROM srs_cards WHERE item_type = ?",
        (zhuyin_course.ITEM_TYPE,),
    ).fetchone()["n"]
    assert n == len(lesson["symbols"])


def test_symbols_are_in_the_daily_review_queue(db):
    """Unlike reading passages, zhuyin joins the main queue: a half-learned
    symbol should come back on its own."""
    assert zhuyin_course.ITEM_TYPE in srs.QUEUE_ITEM_TYPES

    lesson = zhuyin_course.lessons()[0]
    zhuyin_course.record(db, lesson["id"], [{"symbol": s, "correct": True} for s in lesson["symbols"]])

    queue = review.build_queue(db, new_limit=20)
    mine = [i for i in queue if i["item_type"] == zhuyin_course.ITEM_TYPE]
    assert mine, "no zhuyin cards in the queue"
    for item in mine:
        assert item["kind"] == "zhuyin_recall"
        assert item["symbol"] in {s["symbol"] for s in zhuyin_course.symbols()}
        assert item["options"] and sum(1 for o in item["options"] if o["correct"]) == 1
        # Audio is a Han character, as in the course.
        assert item["audio_text"]


def test_a_card_for_a_symbol_that_no_longer_exists_is_skipped(db):
    """The content file is editable; a stale card must not break the queue."""
    srs.ensure_new_card(db, zhuyin_course.ITEM_TYPE, "ㄯ", zhuyin_course.CARD_TYPE)
    db.commit()
    assert review.build_queue(db, new_limit=20) == []


def test_reviewing_a_symbol_schedules_it(db):
    lesson = zhuyin_course.lessons()[0]
    zhuyin_course.record(db, lesson["id"], [{"symbol": s, "correct": True} for s in lesson["symbols"]])
    card_id = review.build_queue(db, new_limit=20)[0]["card_id"]
    out = srs.apply_review(db, card_id, 3)
    assert out["due"]


# ---------------------------------------------------------------------------
# It must not disturb the curriculum
# ---------------------------------------------------------------------------
def test_zhuyin_lessons_do_not_count_as_curriculum_lessons(db):
    """Course progress shares `lesson_progress` with the curriculum, which is
    keyed by id alone. Anything counting rows there has to join `lessons` or it
    will report 注音 lessons as Mandarin ones."""
    from app import tutor

    lesson = zhuyin_course.lessons()[0]
    zhuyin_course.record(db, lesson["id"], [{"symbol": s, "correct": True} for s in lesson["symbols"]])
    assert tutor._current_position(db)["lessons_done"] == 0


def test_the_content_file_is_not_a_curriculum_unit():
    """It lives outside content/units/ deliberately: the scope validator would
    refuse a unit full of bare bopomofo, and rightly so."""
    assert zhuyin_course.CONTENT_PATH.name == "zhuyin.json"
    assert zhuyin_course.CONTENT_PATH.parent.name == "content"
    assert json.loads(zhuyin_course.CONTENT_PATH.read_text(encoding="utf-8"))["symbols"]
