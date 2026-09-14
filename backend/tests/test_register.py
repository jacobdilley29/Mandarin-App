"""Taiwan register in generated text (spec §2).

The scope validator answers "may this sentence use these characters". Nothing
answered "is this how Taiwan says it" — so a generated passage opened with
「早上好」, a greeting no one in Taiwan uses, inside an app whose whole premise is
Taiwan Mandarin. The substitution table already knew 自行車→腳踏車; it had only
ever been applied to imported vocabulary, never to the prose we generate.
"""

from __future__ import annotations

from app import taiwanize
from app.validation import iter_lesson_text, register_slips


def _lesson(**fields) -> dict:
    base = {"id": "l1", "vocab": [], "grammar": [], "sentences": [], "dialogue": []}
    base.update(fields)
    return base


def _data(lesson: dict) -> dict:
    return {"units": [{"id": "u1", "lessons": [lesson]}]}


# ---------------------------------------------------------------------------
# What counts as a slip
# ---------------------------------------------------------------------------
def test_the_greeting_that_started_this(): 
    """早上好 is Mainland. Taiwan says 早安."""
    slips = register_slips(_data(_lesson(passage={"hanzi": "早上好。今天天氣很好。"})))

    assert len(slips) == 1
    assert slips[0].found == [("早上好", "早安")]
    assert slips[0].where == "l1 passage"


def test_a_substitution_the_table_already_knew():
    """自行車→腳踏車 was in the table all along, applied only to vocab import."""
    slips = register_slips(_data(_lesson(dialogue=[{"hanzi": "我騎自行車去。"}])))

    assert slips[0].found == [("自行車", "腳踏車")]


def test_clean_taiwan_text_is_silent():
    lesson = _lesson(
        passage={"hanzi": "早安！我騎腳踏車去便利商店買便當。"},
        dialogue=[{"hanzi": "我搭捷運去。"}],
    )
    assert register_slips(_data(lesson)) == []


def test_several_slips_in_one_string_are_all_named():
    slips = register_slips(_data(_lesson(passage={"hanzi": "早上好，我坐出租車。"})))

    assert slips[0].found == [("出租車", "計程車"), ("早上好", "早安")]


# ---------------------------------------------------------------------------
# Every place a lesson keeps prose
# ---------------------------------------------------------------------------
def test_drill_sentences_are_checked():
    lesson = _lesson(sentences=[{"tokens": ["我", "喜歡", "土豆"]}])
    assert register_slips(_data(lesson))[0].found == [("土豆", "馬鈴薯")]


def test_vocab_examples_are_checked():
    lesson = _lesson(vocab=[{"id": "v1", "traditional": "車",
                             "example": {"hanzi": "這是自行車。"}}])
    assert register_slips(_data(lesson))[0].where == "l1 example[v1]"


def test_grammar_examples_are_checked():
    lesson = _lesson(grammar=[{"id": "g1", "examples": [{"hanzi": "早上好嗎？"}]}])
    assert register_slips(_data(lesson))[0].where == "l1 grammar[g1] ex0"


def test_the_walk_covers_every_field_the_scope_validator_does():
    """The two walks must not drift.

    `passage` had to be added to the scope validator by hand when lessons gained
    one. Anything else walking a lesson would have silently skipped it, which is
    how a check quietly stops covering the newest content.
    """
    import inspect

    from app import validation

    source = inspect.getsource(validation.validate_curriculum)
    walked = {where for where, _ in iter_lesson_text(_lesson(
        vocab=[{"id": "v1", "traditional": "水", "example": {"hanzi": "水"}}],
        grammar=[{"id": "g1", "examples": [{"hanzi": "水"}]}],
        sentences=[{"tokens": ["水"]}],
        dialogue=[{"hanzi": "水"}],
        passage={"hanzi": "水"},
    ))}
    assert len(walked) == 5, "example, grammar example, sentence, dialogue, passage"
    # Each of those field names must appear in the scope validator too.
    for field in ("example", "examples", "sentences", "dialogue", "passage"):
        assert field in source, f"{field} is walked here but not by validate_curriculum"


# ---------------------------------------------------------------------------
# The table itself
# ---------------------------------------------------------------------------
def test_both_tables_feed_one_answer():
    """Substitutions are caught at vocab import, phrases only in prose."""
    forms = taiwanize.prc_forms()

    assert forms["自行車"] == "腳踏車", "from vocabulary.substitutions"
    assert forms["早上好"] == "早安", "from vocabulary.phrases"


def test_the_generator_is_told_about_the_greetings():
    """A check that only reports is a check the next run repeats."""
    from scripts import generate_content as gc

    assert "早安" in gc.SYSTEM_PROMPT and "早上好" in gc.SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Titles — where the real one actually was
# ---------------------------------------------------------------------------
def test_a_passage_title_is_checked():
    """The slip that prompted all of this was in the title, not the body.

    The first pass at this checker walked `passage["hanzi"]` and stopped, which
    would have reported the passage clean and missed 「早上好」 sitting directly
    above it — the single most-read string in the lesson.
    """
    lesson = _lesson(passage={"title": "早上好", "hanzi": "今天天氣很好。"})

    slips = register_slips(_data(lesson))

    assert [s.where for s in slips] == ["l1 passage title"]
    assert slips[0].found == [("早上好", "早安")]


def test_a_lesson_title_is_checked():
    lesson = _lesson(title="騎自行車", passage={"hanzi": "我去學校。"})
    assert register_slips(_data(lesson))[0].where == "l1 title"


def test_titles_are_walked_separately_from_prose():
    """The scope validator checks prose against the character budget and does
    not check titles; the register check must cover both."""
    from app.validation import iter_lesson_titles

    lesson = _lesson(title="打招呼", passage={"title": "早安", "hanzi": "早安。"})

    assert [w for w, _ in iter_lesson_titles(lesson)] == ["l1 title", "l1 passage title"]
    assert [w for w, _ in iter_lesson_text(lesson)] == ["l1 passage"]
