"""Is the curriculum continuous? (spec §3.1)

completeness.py asks whether a unit *has* its parts — examples, grammar,
sentences. This asks a different question, and the one a learner actually feels:

    walking only the units that are live, in order, is every character in this
    lesson one an earlier lesson already taught?

A "hole" is where the answer is no. Two ways to make one, and both have happened:

  Draft hole    A live unit leans on a word taught only in a unit that is still
                a draft. Drafts never appear in Learn, so the learner meets the
                word cold. Six generated units were promoted above thirteen
                unfilled drafts holding 232 words — that is this case.

  Forward reach A lesson uses a word taught in a *later* unit. 較 used in
                u_hsk2_02 but taught in u_hsk3_05; 等 used in u_hsk2_04, taught
                in u_hsk4_01.

Nothing reported either. The content generator validates one unit at a time as
it promotes it, and `make coverage` only ever counted missing pieces, so the
shape of the curriculum as a whole went unexamined.

The check itself is not new machinery: validate_curriculum already accumulates
characters lesson by lesson, so running it over *live units only* answers the
question exactly. This module is the live-only framing plus enough annotation to
make each hole actionable — "taught in u_hsk1_03, still a draft" is a different
job from "taught nowhere at all".

Reporting only. Whether a hole should block anything is a separate decision, and
right now it does not: the draft gate stays as it is.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import curriculum_source
from .validation import placement_pool_chars, validate_curriculum


@dataclass
class Hole:
    """One live lesson reaching for a character no earlier live lesson taught."""

    where: str  # "l_hsk3_07 sentence 2", as validation reports it
    text: str
    char: str
    taught_in: str | None  # unit id, or None when nothing teaches it
    taught_status: str | None  # that unit's status — 'draft' is the usual answer

    @property
    def reason(self) -> str:
        if self.taught_in is None:
            return "taught nowhere in the curriculum"
        if self.taught_status != curriculum_source.STATUS_LIVE:
            return f"taught in {self.taught_in}, still a draft"
        return f"taught in {self.taught_in}, which comes later"


def live_only(data: dict) -> dict:
    """The curriculum as the learner walks it: live units, in order.

    A pure counterpart to curriculum_source.load_live(), which reads from disk —
    this one takes the data it is given so callers and tests can pass anything.
    """
    return {
        "meta": data.get("meta", {}),
        "units": [
            u for u in data.get("units", [])
            if curriculum_source.status_of(u) == curriculum_source.STATUS_LIVE
        ],
    }


def _teaches(data: dict) -> dict[str, tuple[str, str]]:
    """Character -> (unit id, status) of the FIRST unit that teaches it."""
    found: dict[str, tuple[str, str]] = {}
    units = sorted(data.get("units", []), key=lambda u: u.get("sort_order", 0))
    for unit in units:
        status = curriculum_source.status_of(unit)
        for lesson in unit.get("lessons", []):
            for vocab in lesson.get("vocab", []):
                for char in vocab.get("traditional", ""):
                    found.setdefault(char, (unit["id"], status))
    return found


def holes(data: dict) -> list[Hole]:
    """Every place the live sequence asks the learner to read something untaught.

    The placement pool counts as known throughout — those words are seeded as
    mastered before lesson one (see validation.placement_pool_chars).
    """
    result = validate_curriculum(
        live_only(data), extra_known_chars=placement_pool_chars()
    )
    taught = _teaches(data)

    out: list[Hole] = []
    for violation in result.violations:
        for char in violation.unknown:
            unit_id, status = taught.get(char, (None, None))
            out.append(
                Hole(
                    where=violation.where,
                    text=violation.text,
                    char=char,
                    taught_in=unit_id,
                    taught_status=status,
                )
            )
    return out


def summary(data: dict) -> dict:
    """Counts for the coverage report and the JSON output."""
    found = holes(data)
    waiting = sorted({h.taught_in for h in found if h.taught_in and h.taught_status
                      != curriculum_source.STATUS_LIVE})
    return {
        "holes": len(found),
        "lessons_affected": len({h.where.split()[0] for h in found}),
        "characters": sorted({h.char for h in found}),
        "waiting_on_drafts": waiting,
        "taught_nowhere": sorted({h.char for h in found if h.taught_in is None}),
    }
