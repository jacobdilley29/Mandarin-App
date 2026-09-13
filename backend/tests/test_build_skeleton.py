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
