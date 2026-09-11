"""HSK 1–4 curriculum coverage (spec §5).

The permanent answer to "is the whole HSK 1–4 syllabus accounted for, and will
the app present it in order?". These read the committed content, so they fail if
a rebuild drops a word, duplicates one, or scrambles the sequence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import REPO_ROOT

CONTENT = REPO_ROOT / "content"
WORDLISTS = CONTENT / "wordlists"
LEVELS = (1, 2, 3, 4)

# HSK 2.0. The upstream lists are two words short of the nominal 150/300 for
# levels 2 and 3; that is the source's own count, not a dropped word.
EXPECTED_COUNTS = {1: 150, 2: 147, 3: 298, 4: 598}


@pytest.fixture(scope="module")
def curriculum() -> dict:
    return json.loads((CONTENT / "curriculum.json").read_text(encoding="utf-8"))


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
def test_unit_order_is_gapless_and_level_ascending(curriculum):
    orders = [u["sort_order"] for u in curriculum["units"]]
    assert orders == sorted(orders), "units are not in sort_order"
    assert len(set(orders)) == len(orders), "duplicate sort_order"
    assert orders == list(range(1, len(orders) + 1)), "sort_order is not gapless from 1"

    levels = [u["hsk_level"] for u in curriculum["units"]]
    assert levels == sorted(levels), (
        "HSK levels must never go backwards through the curriculum — "
        f"got {levels}"
    )


def test_hand_authored_units_lead_each_level(curriculum):
    """The curated Taiwan units are the thematic hook; a learner should meet
    them before that level's generated vocabulary sets."""
    for level in LEVELS:
        units = [u for u in curriculum["units"] if u["hsk_level"] == level]
        authored = [i for i, u in enumerate(units) if not u.get("generated")]
        made = [i for i, u in enumerate(units) if u.get("generated")]
        if authored and made:
            assert max(authored) < min(made), (
                f"HSK {level}: a generated unit precedes a hand-authored one"
            )


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


def test_whole_corpus_converts_to_zhuyin(curriculum):
    """The phonetic toggle must not silently fall back to pinyin across the
    corpus — a conversion failure means a word the zhuyin setting cannot serve."""
    from app import zhuyin

    failures = []
    for unit in curriculum["units"]:
        for lesson in unit["lessons"]:
            for v in lesson["vocab"]:
                if zhuyin.to_zhuyin(v["pinyin"], v["traditional"]) is None:
                    failures.append((v["traditional"], v["pinyin"]))
    assert not failures, f"{len(failures)} word(s) have no zhuyin: {failures[:10]}"
