"""HSK 1–4 curriculum coverage (spec §5).

The permanent answer to "is the whole HSK 1–4 syllabus accounted for, and will
the app present it in order?". These read the committed content, so they fail if
a rebuild drops a word, duplicates one, or scrambles the sequence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import completeness, curriculum_source
from app.validation import han_chars
from app.config import REPO_ROOT

CONTENT = REPO_ROOT / "content"
WORDLISTS = CONTENT / "wordlists"
LEVELS = (1, 2, 3, 4)

# HSK 2.0. The upstream lists are two words short of the nominal 150/300 for
# levels 2 and 3; that is the source's own count, not a dropped word.
EXPECTED_COUNTS = {1: 150, 2: 147, 3: 298, 4: 598}


@pytest.fixture(scope="module")
def curriculum() -> dict:
    """The whole curriculum — live units and drafts alike.

    Coverage is a question about the source corpus, so drafts count: a word
    staged in a draft unit is accounted for, it just isn't taught yet.
    """
    return curriculum_source.load()


@pytest.fixture(scope="module")
def live() -> dict:
    """Only what the learner can actually reach."""
    return curriculum_source.load_live()


@pytest.fixture(scope="module")
def wordlists() -> dict[int, list[dict]]:
    return {
        level: json.loads((WORDLISTS / f"hsk{level}.json").read_text(encoding="utf-8"))["words"]
        for level in LEVELS
    }


@pytest.fixture(scope="module")
def overrides() -> dict:
    return json.loads((CONTENT / "taiwan_overrides.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def taught(curriculum) -> list[str]:
    """Every word taught by a lesson, in curriculum order (with duplicates)."""
    words = []
    for unit in curriculum["units"]:
        for lesson in unit["lessons"]:
            words.extend(v["traditional"] for v in lesson["vocab"])
    return words


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------
def test_wordlists_have_the_expected_counts(wordlists):
    assert {lv: len(ws) for lv, ws in wordlists.items()} == EXPECTED_COUNTS


def test_every_hsk_word_is_taught_exactly_once(wordlists, overrides, taught, curriculum):
    """No word may be dropped, and none may be taught twice.

    Duplication is not merely untidy: vocab.traditional carries a UNIQUE index,
    so a repeat aborts the content load outright.
    """
    subs = {s["hsk"]: s["taiwan"] for s in overrides["vocabulary"]["substitutions"]}
    pool = {
        v["traditional"]
        for v in json.loads((CONTENT / "hsk1.json").read_text(encoding="utf-8"))["vocab"]
    }

    expected = set()
    for words in wordlists.values():
        for w in words:
            expected.add(subs.get(w["traditional"], w["traditional"]))
    expected -= pool  # the placement pool is taught by placement, not a lesson

    missing = sorted(expected - set(taught))
    assert not missing, f"{len(missing)} HSK word(s) never taught: {missing[:15]}"

    seen, dupes = set(), []
    for w in taught:
        if w in seen:
            dupes.append(w)
        seen.add(w)
    assert not dupes, f"{len(dupes)} word(s) taught more than once: {sorted(set(dupes))[:15]}"


def test_no_simplified_characters_leak_into_the_corpus(curriculum):
    """The app is traditional-only, and the upstream lists put the simplified
    form first for 六 entries (听 for 聽, 几 for 幾). Those are corrected via
    taiwan_overrides.json; this is the guard that they stay corrected."""
    simplified_only = set("听几从离万云买卖东车门问间时长会说话学国语实关点头业书图记论识见风飞马鸟鱼龙")
    offenders = []
    for unit in curriculum["units"]:
        for lesson in unit["lessons"]:
            for v in lesson["vocab"]:
                bad = [c for c in v["traditional"] if c in simplified_only]
                if bad:
                    offenders.append((v["traditional"], bad))
    assert not offenders, f"simplified characters in vocab: {offenders[:10]}"


def test_taiwan_substitutions_are_applied(curriculum, overrides, taught, wordlists):
    """Spec §6: the PRC form must not be what gets taught.

    Only substitutions whose PRC form actually appears in an HSK list can be
    asserted; the file may carry guidance for words outside HSK 1-4, which is a
    harmless no-op here.
    """
    in_lists = {w["traditional"] for words in wordlists.values() for w in words}
    checked = 0
    for sub in overrides["vocabulary"]["substitutions"]:
        assert sub["hsk"] not in taught, f"{sub['hsk']} (PRC form) is still taught"
        if sub["hsk"] not in in_lists:
            continue
        checked += 1
        assert sub["taiwan"] in taught, f"{sub['taiwan']} (Taiwan form) is not taught"
    assert checked, "no substitution matched a word list — is the file wired up?"


def test_pinned_readings_are_applied(curriculum, overrides):
    """The core function words and Taiwan readings must survive a rebuild."""
    by_word = {}
    for unit in curriculum["units"]:
        for lesson in unit["lessons"]:
            for v in lesson["vocab"]:
                by_word[v["traditional"]] = v["pinyin"]

    pinned = {}
    for block in ("core", "spec_6", "full_tone"):
        pinned.update({k: v for k, v in overrides["readings"][block].items() if k != "note"})

    wrong = [
        (w, by_word[w], want)
        for w, want in pinned.items()
        if w in by_word and by_word[w].replace(" ", "") != want.replace(" ", "")
    ]
    assert not wrong, f"pinned readings not applied: {wrong[:10]}"


# ---------------------------------------------------------------------------
# Sequencing
# ---------------------------------------------------------------------------
def test_unit_order_is_gapless(curriculum):
    orders = [u["sort_order"] for u in curriculum["units"]]
    assert orders == sorted(orders), "units are not in sort_order"
    assert len(set(orders)) == len(orders), "duplicate sort_order"
    assert orders == list(range(1, len(orders) + 1)), "sort_order is not gapless from 1"


def test_generated_levels_ascend_among_themselves(curriculum):
    """Within the generated block, HSK levels must not go backwards.

    Deliberately NOT asserted across the whole curriculum. An earlier version
    ordered by level first, which put the HSK 1 generated sets ahead of the
    hand-authored HSK 2-4 Taiwan units and made frequency-ordered word lists the
    first thing in Learn. That got commit 08e90b7 reverted. Authored units now
    lead outright — see the next test.
    """
    levels = [u["hsk_level"] for u in curriculum["units"] if u.get("generated")]
    assert levels == sorted(levels), f"generated units are out of level order: {levels}"


def test_hand_authored_units_lead_the_whole_curriculum(curriculum):
    """便利商店 opens the app, and no generated unit precedes any curated one.

    This is the reverted bug as an assertion. The draft gate already keeps
    unfinished units out of Learn; this makes sure that even after a generated
    unit is completed and promoted, it still does not displace the curated
    Taiwan curriculum Jacob actually wants to start from.
    """
    units = sorted(curriculum["units"], key=lambda u: u["sort_order"])
    authored = [i for i, u in enumerate(units) if not u.get("generated")]
    made = [i for i, u in enumerate(units) if u.get("generated")]

    assert units[0]["id"] == "u_conv", f"curriculum opens with {units[0]['id']}"
    if authored and made:
        assert max(authored) < min(made), "a generated unit precedes a hand-authored one"


def test_generated_units_are_not_taught(live):
    """Whatever the corpus holds, only finished units reach the learner."""
    assert not any(u.get("generated") for u in live["units"])
    assert [u["id"] for u in live["units"]][0] == "u_conv"


def test_every_live_unit_passes_its_completeness_checks(live):
    for report in completeness.evaluate(live):
        assert report.complete, f"{report.unit_id} is live but missing {report.missing}"


def test_every_lesson_is_reachable_by_the_unlock_chain(curriculum):
    """Unlocking is strictly linear, so an empty lesson would wall off the rest."""
    for unit in curriculum["units"]:
        assert unit["lessons"], f"unit {unit['id']} has no lessons"
        for lesson in unit["lessons"]:
            assert lesson["vocab"], (
                f"lesson {lesson['id']} teaches nothing — it cannot be passed, "
                "so every lesson after it is unreachable"
            )


def test_lesson_ids_are_unique(curriculum):
    ids = [l["id"] for u in curriculum["units"] for l in u["lessons"]]
    assert len(set(ids)) == len(ids), "duplicate lesson id"
    unit_ids = [u["id"] for u in curriculum["units"]]
    assert len(set(unit_ids)) == len(unit_ids), "duplicate unit id"


def test_units_carry_their_tocfl_alignment(curriculum):
    mapping = json.loads((CONTENT / "tocfl_mapping.json").read_text(encoding="utf-8"))
    by_hsk = {lv["hsk_level"]: lv for lv in mapping["levels"]}
    for unit in curriculum["units"]:
        expected = by_hsk[unit["hsk_level"]]
        assert unit.get("tocfl_level") == expected["tocfl_level"], unit["id"]
        assert unit.get("tocfl_band") == expected["tocfl_band"], unit["id"]


# ---------------------------------------------------------------------------
# Generated content quality
# ---------------------------------------------------------------------------
def test_lessons_with_sentences_practise_their_own_vocab(curriculum):
    """A drill sentence must exercise the lesson that owns it.

    validate_curriculum accumulates allowed characters monotonically and never
    resets, so by the tail of a 200-lesson curriculum nearly everything is in
    scope and it can no longer catch a lesson whose sentences drifted off its
    own vocabulary. This is the check that still bites there.
    """
    drifted = []
    for unit in curriculum["units"]:
        for lesson in unit["lessons"]:
            sentences = lesson.get("sentences") or []
            if not sentences:
                continue  # not yet generated; vocab-only lessons are valid
            own = set()
            for v in lesson["vocab"]:
                own.update(v["traditional"])
            for i, s in enumerate(sentences):
                text = "".join(s.get("tokens", []))
                if not (set(text) & own):
                    drifted.append(f"{lesson['id']} sentence {i}: {text}")
    assert not drifted, (
        f"{len(drifted)} sentence(s) use none of their lesson's new vocab: {drifted[:10]}"
    )


def test_every_vocab_item_has_a_reading_and_a_gloss(curriculum):
    incomplete = []
    for unit in curriculum["units"]:
        for lesson in unit["lessons"]:
            for v in lesson["vocab"]:
                if not v.get("pinyin") or not v.get("gloss"):
                    incomplete.append(v.get("traditional"))
    assert not incomplete, f"{len(incomplete)} item(s) missing pinyin/gloss: {incomplete[:10]}"

# ---------------------------------------------------------------------------
# Drill quality
# ---------------------------------------------------------------------------
# 現在幾點 ("what time is it now") opens 時間約會. It is natural, high-frequency
# Taiwan usage and a reasonable scene-setter, but it drills neither the lesson's
# vocabulary nor its grammar pattern. Listed rather than rewritten: it is
# hand-authored pedagogical content and changing it is Jacob's call, not a
# test's. Remove the entry if he reworks it.
DRILLS_TEACHING_NEITHER = {"l_time_1": {0}}


def test_every_drill_sentence_exercises_its_lesson(live):
    """A drill that uses none of its lesson's vocabulary or grammar teaches nothing.

    One such sentence shipped in 手搖飲料 (請給我兩杯 — no lesson vocab at all)
    and was caught only by eye during a revert. This is that catch, automated.
    """
    offenders = []
    for unit in live["units"]:
        for lesson in unit["lessons"]:
            vocab = {v["traditional"] for v in lesson.get("vocab") or []}
            # A grammar drill is legitimate: 他吃得很多 exercises 得, not vocab.
            grammar_chars = set()
            for g in lesson.get("grammar") or []:
                grammar_chars |= han_chars(g.get("pattern", "")) | han_chars(g.get("title", ""))

            allowed = DRILLS_TEACHING_NEITHER.get(lesson["id"], set())
            for i, s in enumerate(lesson.get("sentences") or []):
                if i in allowed:
                    continue
                sentence = "".join(s.get("tokens") or [])
                uses_vocab = any(w in sentence for w in vocab)
                uses_grammar = bool(han_chars(sentence) & grammar_chars)
                if not (uses_vocab or uses_grammar):
                    offenders.append(f"{lesson['id']}[{i}] {sentence}")

    assert not offenders, (
        f"{len(offenders)} drill sentence(s) exercise neither their lesson's "
        f"vocabulary nor its grammar: {offenders}"
    )


def test_the_documented_drill_exceptions_still_exist():
    """Stops the allowlist above outliving the content it excuses."""
    for lesson_id, indexes in DRILLS_TEACHING_NEITHER.items():
        lesson = next(
            l for u in curriculum_source.load_live()["units"]
            for l in u["lessons"] if l["id"] == lesson_id
        )
        assert max(indexes) < len(lesson.get("sentences") or []), (
            f"{lesson_id} no longer has sentence {max(indexes)} — drop the exception"
        )


def test_cloze_indexes_point_at_a_real_token(live):
    for unit in live["units"]:
        for lesson in unit["lessons"]:
            for i, s in enumerate(lesson.get("sentences") or []):
                idx, tokens = s.get("cloze_index"), s.get("tokens") or []
                if idx is not None:
                    assert 0 <= idx < len(tokens), f"{lesson['id']}[{i}] cloze_index {idx} of {len(tokens)}"
