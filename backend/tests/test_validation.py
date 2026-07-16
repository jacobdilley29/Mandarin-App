"""Tests for sentence↔vocab validation (spec §5, testing expectations §7)."""

from __future__ import annotations

import json
from pathlib import Path

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
    """The committed seed content must pass vocab validation."""
    data = json.loads((REPO_ROOT / "content" / "curriculum.json").read_text(encoding="utf-8"))
    result = validate_curriculum(data)
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
