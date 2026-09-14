"""Building the curriculum skeleton (spec §3.1).

Two things worth pinning. Themed grouping is now the default — the offline
grouping produces units called "HSK 3 詞彙 7", which is a word-list position
wearing a title, and it was the default for months while the themed path went
unused. And themed grouping needs a key, which it must look for where the user
actually put it: `bin_claude` called `anthropic.Anthropic()` bare, so a key
entered in the app's Me tab themed nothing and failed on auth.
"""

from __future__ import annotations

import json

from scripts import build_skeleton as bs


def test_without_a_key_it_stops_before_doing_any_work(monkeypatch, capsys):
    monkeypatch.setattr(bs, "resolve_api_key", lambda: None)

    assert bs.main(["--dry-run"]) == 1

    out = capsys.readouterr().out
    assert "needs an Anthropic key" in out
    assert "--theme offline" in out, "say how to proceed without one"


def test_offline_still_needs_no_key(monkeypatch, capsys):
    """The no-key path has to keep working, or a fresh checkout can't build."""
    monkeypatch.setattr(bs, "resolve_api_key", lambda: None)

    assert bs.main(["--theme", "offline", "--dry-run"]) == 0
    assert "would write" in capsys.readouterr().out


def test_the_default_is_themed_not_offline(monkeypatch, capsys):
    """The offline grouping was the default for months, and produces units
    called "HSK 3 詞彙 7" — a word-list position wearing a title. Asserted
    through behaviour, since main() builds its parser inline: with no key, the
    default path is the one that stops and asks for a key."""
    monkeypatch.setattr(bs, "resolve_api_key", lambda: None)

    assert bs.main(["--dry-run"]) == 1, "the default must be the themed path"


# ---------------------------------------------------------------------------
# A level that fails must not take the run down with it
# ---------------------------------------------------------------------------
def test_the_token_budget_scales_with_the_level(): 
    """A flat budget fits the smallest level and nothing else.

    HSK 4 is 590 words against HSK 1's 106, and its plan is proportionally
    longer — while adaptive thinking draws from the same allowance.
    """
    assert bs.theme_budget(590) > bs.theme_budget(106)
    assert bs.theme_budget(106) >= 16000, "never budget less than the old flat value"


class _Truncated:
    """What a response cut off at the token limit actually looks like."""

    parsed_output = None
    stop_reason = "max_tokens"

    class usage:  # noqa: D106
        output_tokens = 16000


class _Empty:
    parsed_output = None
    stop_reason = "end_turn"


def test_a_truncated_plan_says_it_was_truncated(): 
    """The failure mode that does not look like itself.

    parsed_output is None either way, so without this the error reads "no plan
    came back" — which sends you looking at your key and your model, not at a
    token limit.
    """
    import pytest

    with pytest.raises(RuntimeError, match="cut off at the token limit"):
        bs._plan_from_response(_Truncated(), 2)


def test_an_empty_plan_reports_its_stop_reason(): 
    import pytest

    with pytest.raises(RuntimeError, match="end_turn"):
        bs._plan_from_response(_Empty(), 2)


def _stub_levels(monkeypatch, failing: int):
    """Theme every level, except `failing`, which raises."""
    def fake(words, level, existing, per_lesson, refresh):
        if level == failing:
            raise RuntimeError("boom")
        units = bs.bin_offline(words, level, per_lesson, lessons_per_unit=3)
        for i, u in enumerate(units, start=1):
            u["title"] = f"主題 HSK{level}-{i}"
        return units, []

    monkeypatch.setattr(bs, "bin_claude", fake)
    monkeypatch.setattr(bs, "resolve_api_key", lambda: "sk-test")


def test_one_failed_level_does_not_stop_the_others(monkeypatch, capsys):
    """Aborting throws away the levels that succeeded — and their plans cost money."""
    _stub_levels(monkeypatch, failing=2)

    assert bs.main(["--dry-run"]) == 1, "a stalled level is still a failed run"

    out = capsys.readouterr().out
    assert "✗ HSK 2" in out
    assert "HSK 1:" in out and "HSK 3:" in out, "other levels must still be themed"
    assert "would write" in out, "the run reaches the end and reports what it built"


def test_a_failed_level_keeps_its_existing_units(monkeypatch, capsys):
    """Dropping them would delete paid-for lesson content and fail coverage.

    The level's words are not missing — they are exactly where they were — so
    the coverage assertion must not fire on them.
    """
    _stub_levels(monkeypatch, failing=2)

    assert bs.main(["--dry-run"]) == 1
    out = capsys.readouterr().out
    assert "never placed" not in out, "the stalled level's words are still placed"
    assert "leaving HSK 2 as it is" in out


def test_a_stalled_run_warns_against_generating_into_it(monkeypatch, capsys):
    """The expensive mistake: generating into a level that was never regrouped.

    Its words get regrouped by the re-theme that eventually succeeds, and the
    cache treats a changed word set as a miss — so the content is paid for twice.
    """
    _stub_levels(monkeypatch, failing=2)

    bs.main(["--dry-run"])

    out = capsys.readouterr().out
    assert "paid for twice" in out
    assert "cached" in out, "say that retrying costs nothing for levels that worked"


# ---------------------------------------------------------------------------
# The reading-fix path, which no test had ever executed
# ---------------------------------------------------------------------------
def test_a_plan_s_reading_fixes_are_applied(monkeypatch, tmp_path):
    """This path called a function that does not exist.

    `_norm_pinyin` was never defined anywhere — a NameError sitting in
    bin_claude, waiting for the first plan whose reading_fixes list was
    non-empty. Which is to say: it fired on the very first real themed build,
    after the API call had been made and paid for, and after the plan had been
    cached. Nothing caught it because no test had ever run bin_claude at all.

    Driven through the plan cache, so it needs no key and makes no call.
    """
    monkeypatch.setattr(bs, "CACHE_DIR", tmp_path)
    (tmp_path / "skeleton-hsk1.json").write_text(
        json.dumps(
            {
                "units": [{"title": "打招呼", "subtitle": "Greetings",
                           "lessons": [{"title": "你好", "words": ["喜歡", "朋友"]}]}],
                # The model correcting a mainland reading to the Taiwan one.
                "reading_fixes": [
                    {"traditional": "喜歡", "pinyin": "xǐhuān", "why": "Taiwan reading"}
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    words = [
        {"traditional": "喜歡", "pinyin": "xǐ huan", "gloss": "to like",
         "hsk_level": 1, "bopomofo": "ㄒㄧˇ ˙ㄏㄨㄢ"},
        {"traditional": "朋友", "pinyin": "péngyǒu", "gloss": "friend", "hsk_level": 1},
    ]

    units, fixes = bs.bin_claude(words, 1, existing=[], per_lesson=6, refresh=False)

    assert len(fixes) == 1
    assert words[0]["pinyin"] == "xǐhuān", "the corrected reading must be applied"
    assert "bopomofo" not in words[0], "a stale zhuyin from the old reading must go"
    assert units[0]["title"] == "打招呼", "and the themed title still comes through"


def test_a_reading_fix_that_agrees_changes_nothing(monkeypatch, tmp_path):
    """Spacing and Unicode form must not read as a disagreement."""
    monkeypatch.setattr(bs, "CACHE_DIR", tmp_path)
    (tmp_path / "skeleton-hsk1.json").write_text(
        json.dumps(
            {
                "units": [{"title": "打招呼", "subtitle": "Greetings",
                           "lessons": [{"title": "你好", "words": ["朋友"]}]}],
                "reading_fixes": [
                    {"traditional": "朋友", "pinyin": "péng yǒu", "why": "same reading, spaced"}
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    words = [{"traditional": "朋友", "pinyin": "péngyǒu", "gloss": "friend",
              "hsk_level": 1, "bopomofo": "ㄆㄥˊ ㄧㄡˇ"}]

    bs.bin_claude(words, 1, existing=[], per_lesson=6, refresh=False)

    assert words[0]["pinyin"] == "péngyǒu", "an agreeing fix must not rewrite the reading"
    assert words[0]["bopomofo"] == "ㄆㄥˊ ㄧㄡˇ", "nor discard its zhuyin"


# ---------------------------------------------------------------------------
# Chunking — because a whole level does not fit in one response
# ---------------------------------------------------------------------------
def _words(n: int, start: int = 0) -> list[dict]:
    return [
        {"traditional": f"詞{i}", "pinyin": f"ci{i}", "gloss": f"word {i}", "hsk_level": 2}
        for i in range(start, start + n)
    ]


def _capture_calls(monkeypatch, tmp_path):
    """Replace the API call with a recorder that themes whatever it is given."""
    monkeypatch.setattr(bs, "CACHE_DIR", tmp_path)
    calls = []

    def fake(words, level, existing, per_lesson, label):
        calls.append({"n": len(words), "existing": list(existing), "label": label})
        return {
            "units": [{
                "title": f"主題{len(calls)}",
                "subtitle": "theme",
                "lessons": [{"title": "一", "words": [w["traditional"] for w in words]}],
            }],
            "reading_fixes": [],
        }

    monkeypatch.setattr(bs, "_theme_call", fake)
    return calls


def test_a_level_too_big_for_one_response_is_themed_in_chunks(monkeypatch, tmp_path):
    """Measured: 106 words fit in 16000 tokens, 129 did not. HSK 4 is 590."""
    calls = _capture_calls(monkeypatch, tmp_path)
    words = _words(bs.CHUNK_WORDS * 2 + 5)

    units, _ = bs.bin_claude(words, 2, existing=[], per_lesson=6, refresh=False)

    assert len(calls) == 3, "three chunks for two-and-a-bit chunks' worth of words"
    assert [c["n"] for c in calls] == [bs.CHUNK_WORDS, bs.CHUNK_WORDS, 5]
    placed = [v["traditional"] for u in units for l in u["lessons"] for v in l["vocab"]]
    assert len(placed) == len(words), "every word still lands somewhere"


def test_each_chunk_is_told_the_themes_already_chosen(monkeypatch, tmp_path):
    """Otherwise the second half of a level invents 夜市 a second time."""
    calls = _capture_calls(monkeypatch, tmp_path)

    bs.bin_claude(_words(bs.CHUNK_WORDS + 1), 2, existing=["便利商店"], per_lesson=6,
                  refresh=False)

    assert calls[0]["existing"] == ["便利商店"]
    assert calls[1]["existing"] == ["便利商店", "主題1"], "chunk 2 sees chunk 1's theme"


def test_a_chunk_is_cached_on_its_own(monkeypatch, tmp_path):
    """So a failure costs only the chunk it happened in, not the level."""
    calls = _capture_calls(monkeypatch, tmp_path)
    words = _words(bs.CHUNK_WORDS + 1)

    bs.bin_claude(words, 2, existing=[], per_lesson=6, refresh=False)
    assert len(calls) == 2
    assert (tmp_path / "skeleton-hsk2-01.json").is_file()
    assert (tmp_path / "skeleton-hsk2-02.json").is_file()

    bs.bin_claude(words, 2, existing=[], per_lesson=6, refresh=False)
    assert len(calls) == 2, "a second run must cost nothing"


def test_a_whole_level_plan_from_before_chunking_is_still_honoured(monkeypatch, tmp_path):
    """Re-theming a level that is already planned costs money AND regroups its
    words, which throws away every lesson generated under it."""
    calls = _capture_calls(monkeypatch, tmp_path)
    (tmp_path / "skeleton-hsk2.json").write_text(
        json.dumps({"units": [{"title": "夜市", "subtitle": "Night market",
                               "lessons": [{"title": "一", "words": ["詞0"]}]}],
                    "reading_fixes": []}, ensure_ascii=False),
        encoding="utf-8",
    )

    units, _ = bs.bin_claude(_words(1), 2, existing=[], per_lesson=6, refresh=False)

    assert calls == [], "a level with a whole-level plan must not be re-themed"
    assert units[0]["title"] == "夜市"


def test_the_budget_covers_what_a_chunk_actually_needs(): 
    """129 words exhausted 16000 tokens in the real run that found this.

    A chunk is CHUNK_WORDS, so its budget has to sit well clear of that per-word
    rate, and under a ceiling the API will accept.
    """
    per_word_that_failed = 16000 / 129
    assert bs.theme_budget(bs.CHUNK_WORDS) > bs.CHUNK_WORDS * per_word_that_failed * 1.5
    assert bs.theme_budget(10_000) <= 32000, "never ask for more than the API allows"


# ---------------------------------------------------------------------------
# The draft gate — a unit straight out of theming is not teachable
# ---------------------------------------------------------------------------
def test_a_themed_unit_comes_out_as_a_draft(monkeypatch, tmp_path):
    """The test that was missing, and the bug it would have caught.

    bin_offline sets status=draft with a comment explaining why. bin_claude
    built its unit dict without a status at all, and `status_of` defaults to
    **live** — so a forgotten field is not a missing status, it is the wrong
    one. The first complete themed build reported "84 live · 0 draft" and had
    70 units whose lessons held vocabulary and nothing else: no grammar, no
    sentences, no dialogue, ready to be loaded and taught.

    This is the failure app/completeness.py was written to prevent; its
    docstring names the commit that had to be reverted over it.
    """
    _capture_calls(monkeypatch, tmp_path)

    units, _ = bs.bin_claude(_words(3), 2, existing=[], per_lesson=6, refresh=False)

    assert units, "the theming must actually produce units"
    for u in units:
        assert bs.curriculum_source.status_of(u) == bs.curriculum_source.STATUS_DRAFT
        # The reason it must be a draft, stated as the test's own premise.
        assert all(not l["sentences"] and not l["grammar"] for l in u["lessons"])


def test_the_offline_path_is_still_a_draft_too(monkeypatch, tmp_path):
    units = bs.bin_offline(_words(3), 2, per_lesson=6, lessons_per_unit=3)
    assert all(
        bs.curriculum_source.status_of(u) == bs.curriculum_source.STATUS_DRAFT
        for u in units
    )


def test_an_unfinished_generated_unit_is_staged_before_writing():
    """The invariant, checked once, rather than trusted to every binning path."""
    unit = {
        "id": "u_hsk2_01", "title": "夜市", "generated": True, "status": "live",
        "lessons": [{"id": "l1", "vocab": [{"traditional": "水", "pinyin": "shuǐ",
                                            "gloss": "water"}],
                     "grammar": [], "sentences": [], "dialogue": []}],
    }

    staged = bs._stage_unfinished([unit])

    assert staged == ["u_hsk2_01"]
    assert unit["status"] == bs.curriculum_source.STATUS_DRAFT


def test_a_finished_generated_unit_is_left_live():
    """A stalled level reuses its existing units, which may be finished."""
    unit = {
        "id": "u_hsk2_01", "title": "夜市", "generated": True, "status": "live",
        "lessons": [{
            "id": "l1",
            "vocab": [{"traditional": "水", "pinyin": "shuǐ", "gloss": "water",
                       "example": {"hanzi": "我喝水"}}],
            "grammar": [{"id": "g1"}],
            "sentences": [{"tokens": ["水"]}],
            "dialogue": [{"hanzi": "水"}],
        }],
    }

    assert bs._stage_unfinished([unit]) == []
    assert unit["status"] == "live"


def test_a_hand_authored_unit_without_a_status_stays_live():
    """status_of defaults to live for exactly this case — don't break it."""
    unit = {"id": "u_conv", "title": "便利商店",
            "lessons": [{"id": "l1", "vocab": [], "grammar": [],
                         "sentences": [], "dialogue": []}]}

    assert bs._stage_unfinished([unit]) == []
    assert "status" not in unit


# ---------------------------------------------------------------------------
# Titles the learner actually reads
# ---------------------------------------------------------------------------
def _titled(unit_title: str, *lesson_titles: str) -> dict:
    return {
        "id": "u_hsk2_01", "title": unit_title, "generated": True, "status": "draft",
        "lessons": [{"id": f"l_{i}", "title": t}
                    for i, t in enumerate(lesson_titles, start=1)],
    }


def test_english_leaking_into_a_chinese_title_is_reported():
    """A real one from the first themed build, in a LESSON title.

    The prompt rule covered unit titles and said nothing about lesson titles,
    so "describe 一個人的樣子" shipped — and that is exactly the string the
    learner sees in the app.
    """
    found = bs.latin_in_titles([_titled("逛街買東西", "describe 一個人的樣子")])

    assert [t for _, t in found] == ["describe 一個人的樣子"]


def test_a_clean_chinese_title_is_not_reported():
    assert bs.latin_in_titles([_titled("逛街買東西", "買衣服、試穿", "顏色和比較")]) == []


def test_taiwanese_terms_written_in_latin_are_fine():
    """3C產品, MRT and KTV are how Taiwan actually writes these."""
    assert bs.latin_in_titles([_titled("搭捷運", "MRT 路線", "去 KTV 唱歌")]) == []


def test_a_unit_title_is_checked_too():
    found = bs.latin_in_titles([_titled("shopping 逛街", "買衣服")])
    assert [t for _, t in found] == ["shopping 逛街"]


def test_hand_authored_titles_are_left_alone():
    """The curated units are Jacob's own wording, not the model's."""
    unit = _titled("describe 一個人", "x")
    del unit["generated"]
    assert bs.latin_in_titles([unit]) == []


def test_the_theming_prompt_asks_for_chinese_lesson_titles():
    """The rule that was missing. Asking is not getting — hence the report
    above — but a prompt that never asked was the root of it."""
    assert "lesson titles in Traditional Chinese" in bs.THEME_SYSTEM
