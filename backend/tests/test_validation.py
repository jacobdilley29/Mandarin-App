"""Tests for sentence↔vocab validation (spec §5, testing expectations §7)."""

from __future__ import annotations

import json
from pathlib import Path

from app import curriculum_source, validation
from app.config import REPO_ROOT
from app.validation import (
    allowed_chars,
    check_sentence,
    han_chars,
    validate_curriculum,
)


def test_han_chars_extracts_only_han():
    assert han_chars("我要一杯水。") == {"我", "要", "一", "杯", "水"}
    # Latin, digits, punctuation dropped.
    assert han_chars("A1 你好, world!") == {"你", "好"}
    assert han_chars("") == set()


def test_allowed_chars_union():
    allowed = allowed_chars(["便當", "水"], ["我", "要"])
    assert allowed == {"便", "當", "水", "我", "要"}


def test_check_sentence_flags_unknown():
    allowed = {"我", "要", "水"}
    assert check_sentence("我要水", allowed) == set()
    assert check_sentence("我要珍珠", allowed) == {"珍", "珠"}


def test_seed_curriculum_is_valid():
    """The committed curriculum must pass vocab validation under real loading
    conditions — i.e. with the HSK 1 placement pool treated as pre-known, exactly
    as scripts/load_content.py does."""
    # Through the source loader, not the raw file: since the split (spec §3.1)
    # curriculum.json is a manifest and the content lives in content/units/.
    data = curriculum_source.load()
    hsk1 = json.loads((REPO_ROOT / "content" / "hsk1.json").read_text(encoding="utf-8"))
    hsk1_chars: set[str] = set()
    for v in hsk1.get("vocab", []):
        hsk1_chars |= han_chars(v["traditional"])
    result = validate_curriculum(data, extra_known_chars=hsk1_chars)
    assert result.ok, "seed content has vocab violations: " + "; ".join(
        f"[{v.where}] {v.text} -> {v.unknown}" for v in result.violations
    )


def test_validate_curriculum_detects_out_of_scope():
    data = {
        "meta": {"function_words": ["我", "要"]},
        "units": [
            {
                "id": "u1",
                "title": "t",
                "sort_order": 1,
                "lessons": [
                    {
                        "id": "l1",
                        "title": "t",
                        "sort_order": 1,
                        "vocab": [{"id": "v1", "traditional": "水", "pinyin": "shuǐ", "gloss": "water"}],
                        "grammar": [],
                        "dialogue": [],
                        # 珍珠 is not in scope (only 我/要/水 known).
                        "sentences": [{"tokens": ["我", "要", "珍珠"], "cloze_index": 2}],
                    }
                ],
            }
        ],
    }
    result = validate_curriculum(data)
    assert not result.ok
    # The unknown set contains the out-of-scope characters.
    unknown = set(result.violations[0].unknown)
    assert {"珍", "珠"} <= unknown


# ---------------------------------------------------------------------------
# The placement pool is in scope from lesson one
# ---------------------------------------------------------------------------
def _one_lesson(sentence_tokens: list[str], teaches: str) -> dict:
    return {"meta": {"function_words": []}, "units": [{
        "id": "u", "sort_order": 1, "lessons": [{
            "id": "l", "sort_order": 1,
            "vocab": [{"id": "v", "traditional": teaches}],
            "sentences": [{"tokens": sentence_tokens}],
        }]}]}


def test_the_placement_pool_is_known_before_any_lesson():
    """老師 and 學校 are seeded as mastered at placement, never taught.

    They must therefore be usable in lesson one. The generator did not know
    this and rejected 17 of 23 units for writing ordinary Taiwanese.
    """
    data = _one_lesson(["老師", "講"], teaches="講")

    assert validation.validate_curriculum(data).violations, "bare check should object"

    pooled = validation.validate_curriculum(
        data, extra_known_chars=validation.placement_pool_chars()
    )
    unknown = {c for v in pooled.violations for c in v.unknown}
    assert not (unknown & set("老師")), f"pool words still rejected: {unknown}"


def test_the_pool_helper_actually_finds_the_pool():
    """A silently-empty pool would make the fix a no-op and nobody would notice."""
    words = validation.placement_pool_words()

    assert len(words) > 20, "the placement pool should not be empty"
    assert "老師" in words and "朋友" in words
    assert set("老師朋友") <= validation.placement_pool_chars()


def test_a_genuinely_untaught_word_is_still_rejected():
    """The gate still has to work — this is not a licence to write anything."""
    data = _one_lesson(["老師", "嚇", "到"], teaches="講")

    pooled = validation.validate_curriculum(
        data, extra_known_chars=validation.placement_pool_chars()
    )
    assert "嚇" in {c for v in pooled.violations for c in v.unknown}
