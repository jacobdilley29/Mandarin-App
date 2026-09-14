"""Per-unit completeness tracking and the draft gate (spec §3.1).

The spec asks for completeness to be tracked explicitly, "so a half-populated
level is visible rather than silently passing as done". This module is that
tracking, and it is also the gate that decides what the learner ever sees.

It exists because of a specific failure. An earlier attempt to grow the
curriculum from 149 to 1,208 words (commit 08e90b7) generated the vocabulary
mechanically and shipped it: 63 units of frequency-ordered words with raw
dictionary glosses, no example sentences, no dialogues, no grammar — ordered
ahead of the hand-authored Taiwan units, so they became the first thing in
Learn. The pass that would have written the sentences could not run. The whole
thing was reverted.

The lesson is not "don't generate content". It is that generated content must
not be able to reach the learner until it is finished. So completeness is
computed from the source, and `content.get_curriculum()` serves live units only.
A unit missing sentences cannot be taught, cannot be unlocked, and cannot
displace a finished unit — regardless of its sort_order, and regardless of
anyone remembering to check.

A check that is *required* gates the unit. Optional checks are reported but do
not block, so the report stays informative without being precious.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .curriculum_source import STATUS_DRAFT, STATUS_LIVE

# (key, required, description)
CHECKS: tuple[tuple[str, bool, str], ...] = (
    ("has_lessons", True, "unit contains at least one lesson"),
    ("vocab_seeded", True, "every lesson introduces vocabulary"),
    ("vocab_glossed", True, "every vocab item has a gloss and a reading"),
    ("examples_present", True, "every vocab item has an example sentence"),
    ("grammar_seeded", True, "every lesson introduces a grammar point"),
    ("sentences_present", True, "every lesson has drill sentences"),
    ("dialogue_present", False, "every lesson has a dialogue"),
    ("passage_present", False, "every lesson has a reading passage"),
    ("taiwan_notes", False, "at least one Taiwan usage note in the unit"),
)

REQUIRED = tuple(key for key, required, _ in CHECKS if required)
DESCRIPTIONS = {key: description for key, _, description in CHECKS}


@dataclass
class UnitCompleteness:
    unit_id: str
    title: str
    checks: dict[str, bool] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def missing(self) -> list[str]:
        """Required checks that fail — the reason a unit is still a draft."""
        return [k for k in REQUIRED if not self.checks.get(k)]

    @property
    def missing_optional(self) -> list[str]:
        return [k for k, req, _ in CHECKS if not req and not self.checks.get(k)]

    @property
    def complete(self) -> bool:
        return not self.missing

    @property
    def status(self) -> str:
        return STATUS_LIVE if self.complete else STATUS_DRAFT

    def as_dict(self) -> dict:
        return {
            "unit_id": self.unit_id,
            "title": self.title,
            "complete": self.complete,
            "status": self.status,
            "checks": self.checks,
            "counts": self.counts,
            "missing": self.missing,
            "missing_optional": self.missing_optional,
        }


def evaluate_unit(unit: dict) -> UnitCompleteness:
    """Run every check against one unit's source."""
    lessons = unit.get("lessons") or []
    all_vocab = [v for l in lessons for v in (l.get("vocab") or [])]

    counts = {
        "lessons": len(lessons),
        "vocab": len(all_vocab),
        "grammar": sum(len(l.get("grammar") or []) for l in lessons),
        "sentences": sum(len(l.get("sentences") or []) for l in lessons),
        "dialogue_lines": sum(len(l.get("dialogue") or []) for l in lessons),
        "examples": sum(1 for v in all_vocab if (v.get("example") or {}).get("hanzi")),
        "taiwan_notes": sum(1 for v in all_vocab if v.get("taiwan_note")),
    }

    checks = {
        "has_lessons": bool(lessons),
        # `all(...)` over an empty list is True, so each of these is anchored on
        # the unit having lessons at all — otherwise an empty unit passes
        # everything and goes live with nothing in it.
        "vocab_seeded": bool(lessons) and all(l.get("vocab") for l in lessons),
        "vocab_glossed": bool(all_vocab)
        and all(v.get("gloss") and v.get("pinyin") for v in all_vocab),
        "examples_present": bool(all_vocab)
        and all((v.get("example") or {}).get("hanzi") for v in all_vocab),
        "grammar_seeded": bool(lessons) and all(l.get("grammar") for l in lessons),
        "sentences_present": bool(lessons) and all(l.get("sentences") for l in lessons),
        "dialogue_present": bool(lessons) and all(l.get("dialogue") for l in lessons),
        "passage_present": bool(lessons) and all(
            (l.get("passage") or {}).get("hanzi") for l in lessons
        ),
        "taiwan_notes": counts["taiwan_notes"] > 0,
    }

    return UnitCompleteness(
        unit_id=unit.get("id", "?"),
        title=unit.get("title", ""),
        checks=checks,
        counts=counts,
    )


def evaluate(data: dict) -> list[UnitCompleteness]:
    """Completeness for every unit in a merged curriculum, in curriculum order."""
    units = sorted(data.get("units", []), key=lambda u: u.get("sort_order", 0))
    return [evaluate_unit(u) for u in units]


def resolved_status(unit: dict) -> str:
    """The status a unit actually gets, reconciling its source with the checks.

    A unit marked live that fails a required check is demoted to draft. Marking
    a unit live cannot override the checks — otherwise the gate is only as good
    as whoever last edited the file, which is exactly how the reverted content
    reached Learn.
    """
    declared = unit.get("status", STATUS_LIVE)
    if declared != STATUS_LIVE:
        return declared
    return evaluate_unit(unit).status


def summary(data: dict) -> dict:
    """Coverage report for `make coverage` and GET /api/content/coverage."""
    reports = evaluate(data)
    units_by_id = {u.get("id"): u for u in data.get("units", [])}

    live = [r for r in reports if resolved_status(units_by_id.get(r.unit_id, {})) == STATUS_LIVE]
    draft = [r for r in reports if r not in live]

    def totals(reports_: list[UnitCompleteness]) -> dict[str, int]:
        keys = ("lessons", "vocab", "grammar", "sentences", "dialogue_lines")
        return {k: sum(r.counts.get(k, 0) for r in reports_) for k in keys}

    return {
        "units": len(reports),
        "live": len(live),
        "draft": len(draft),
        "totals": {"all": totals(reports), "live": totals(live), "draft": totals(draft)},
        "checks": {key: DESCRIPTIONS[key] for key in DESCRIPTIONS},
        "required": list(REQUIRED),
        "report": [r.as_dict() for r in reports],
    }
