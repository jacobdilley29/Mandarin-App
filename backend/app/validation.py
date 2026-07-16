"""Sentence ↔ vocab validation (spec §5).

Every sentence used in a lesson must be expressible from the vocabulary the
learner has met by that point in the curriculum, plus a small allowlist of
function words. This guards hand-authored and Claude-generated content alike:
the content pipeline flags any sentence that introduces an unknown character so
it can be regenerated.

The check is at the *character* level (the unit a learner actually decodes),
ignoring punctuation and latin/digits.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# CJK Unified Ideographs (incl. common extension A). Good enough for HSK-range
# Traditional text.
_HAN_RE = re.compile(r"[㐀-䶿一-鿿]")


def han_chars(text: str) -> set[str]:
    """The set of Han characters in a string (drops punctuation/latin/digits)."""
    return set(_HAN_RE.findall(text))


@dataclass
class Violation:
    where: str  # human-readable location, e.g. "l_conv_1 sentence 3"
    text: str  # the offending sentence
    unknown: list[str]  # characters not in the allowed set


@dataclass
class ValidationResult:
    violations: list[Violation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def add(self, where: str, text: str, unknown: set[str]) -> None:
        if unknown:
            self.violations.append(
                Violation(where=where, text=text, unknown=sorted(unknown))
            )


def allowed_chars(
    vocab_traditional: list[str], function_words: list[str]
) -> set[str]:
    """Build the allowed character set from known words + function words."""
    allowed: set[str] = set()
    for w in vocab_traditional:
        allowed |= han_chars(w)
    for w in function_words:
        allowed |= han_chars(w)
    return allowed


def check_sentence(text: str, allowed: set[str]) -> set[str]:
    """Return the set of Han characters in `text` not present in `allowed`."""
    return han_chars(text) - allowed


def validate_curriculum(data: dict) -> ValidationResult:
    """Validate a curriculum JSON payload (the shape of content/curriculum.json).

    Characters accumulate lesson-by-lesson: a sentence in lesson N may use any
    vocab from lessons 1..N (plus the global function-word allowlist), matching
    how the learner progresses.
    """
    result = ValidationResult()
    function_words = data.get("meta", {}).get("function_words", [])
    base_allowed = allowed_chars([], function_words)

    cumulative = set(base_allowed)

    # Flatten units/lessons in curriculum order.
    units = sorted(data.get("units", []), key=lambda u: u.get("sort_order", 0))
    for unit in units:
        lessons = sorted(unit.get("lessons", []), key=lambda l: l.get("sort_order", 0))
        for lesson in lessons:
            lid = lesson.get("id", "?")

            # This lesson's new vocab becomes known for its own drills.
            for v in lesson.get("vocab", []):
                cumulative |= han_chars(v["traditional"])

            # A grammar point introduces its own pattern characters (e.g. 只, 用,
            # 還是), so those count as known for this lesson's sentences too.
            for g in lesson.get("grammar", []):
                cumulative |= han_chars(g.get("pattern", ""))
                cumulative |= han_chars(g.get("title", ""))

            # Validate example sentences on the new vocab.
            for v in lesson.get("vocab", []):
                ex = v.get("example") or {}
                if ex.get("hanzi"):
                    unknown = check_sentence(ex["hanzi"], cumulative)
                    result.add(f"{lid} example[{v['id']}]", ex["hanzi"], unknown)

            # Validate grammar examples.
            for g in lesson.get("grammar", []):
                for i, ex in enumerate(g.get("examples", [])):
                    if ex.get("hanzi"):
                        unknown = check_sentence(ex["hanzi"], cumulative)
                        result.add(f"{lid} grammar[{g['id']}] ex{i}", ex["hanzi"], unknown)

            # Validate drill sentences.
            for i, s in enumerate(lesson.get("sentences", [])):
                sent = "".join(s.get("tokens", []))
                unknown = check_sentence(sent, cumulative)
                result.add(f"{lid} sentence {i}", sent, unknown)

            # Dialogue lines are naturally a bit richer (they set the scene);
            # validate them but they share the same cumulative budget.
            for i, line in enumerate(lesson.get("dialogue", [])):
                if line.get("hanzi"):
                    unknown = check_sentence(line["hanzi"], cumulative)
                    result.add(f"{lid} dialogue {i}", line["hanzi"], unknown)

    return result
