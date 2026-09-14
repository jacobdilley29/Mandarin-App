"""Put the curriculum in level order — and measure what that costs first.

The Learn map currently teaches every hand-authored unit before any generated
one. Those authored units are HSK 2-4, so a learner meets 銀行郵局 and 手機網路
before the generated HSK 1 material. That ordering was a deliberate reaction to
a real failure — generated units were once unthemed word bags with no sentences
at all, and level-ordering put them at the very front of Learn (see assemble()
in build_skeleton.py, and the commit it names). Now that generated units are
themed, complete and gated, that reason has expired.

**Reordering is not cosmetic.** Character scope is cumulative in sort_order: a
lesson may use anything taught before it. Generated HSK 2 content was written
knowing all fourteen authored units came first, so moving it ahead of the
authored HSK 3-4 units can put sentences out of scope that were in scope when
they were generated and paid for.

So this reports before it writes, and it only ever rewrites `sort_order` — never
a lesson. (Do not reach for `make build-skeleton` to fix ordering: that rebuilds
generated units from their theming plans and would discard every generated
lesson with them.)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import curriculum_source  # noqa: E402
from app.validation import placement_pool_chars, validate_curriculum  # noqa: E402


def level_order(units: list[dict]) -> list[dict]:
    """Every unit by level, hand-authored first within each level.

    The thorough answer, and the expensive one. It moves generated units ahead of
    authored units a level above them, which removes that authored vocabulary
    from what their sentences may use — see the module docstring.
    """
    return sorted(
        units,
        key=lambda u: (
            u.get("hsk_level") or 0,
            1 if u.get("generated") else 0,
            u.get("sort_order", 0),
        ),
    )


def beginner_first(units: list[dict]) -> list[dict]:
    """Generated HSK 1 units first; everything else exactly where it was.

    This is the surgical version. The complaint is that a beginner meets 銀行郵局
    before any HSK 1 material, and moving just the HSK 1 units answers it. Because
    nothing else changes position, no other unit loses a word it was written
    against: moving a unit *earlier* only ever shrinks its own allowed
    vocabulary, and everything after it gains the HSK 1 words rather than losing
    anything.

    The HSK 1 units themselves do break, and should: they were generated sitting
    behind all fourteen authored units, so they were written with 捷運 and 悠遊卡
    available. A greetings lesson that needs an EasyCard is not an HSK 1 lesson.
    Regenerating them in their proper position is the point, not a side effect.
    """
    first = [u for u in units if u.get("generated") and (u.get("hsk_level") or 0) == 1]
    rest = [u for u in units if u not in first]
    first.sort(key=lambda u: u.get("sort_order", 0))
    rest.sort(key=lambda u: u.get("sort_order", 0))
    return first + rest


STRATEGIES = {"beginner-first": beginner_first, "level": level_order}

# More out-of-scope sentences than a curriculum picks up in normal authoring.
# Past this, the working tree has almost certainly had a reorder applied without
# the regeneration that was supposed to follow it.
DIRTY_BASELINE = 50


def renumbered(units: list[dict], strategy: str = "beginner-first") -> list[dict]:
    out = []
    for i, unit in enumerate(STRATEGIES[strategy](units), start=1):
        copy = dict(unit)
        copy["sort_order"] = i
        out.append(copy)
    return out


def _violations(data: dict) -> dict[str, set[str]]:
    result = validate_curriculum(data, extra_known_chars=placement_pool_chars())
    by_where: dict[str, set[str]] = {}
    for v in result.violations:
        by_where.setdefault(v.where, set()).update(v.unknown)
    return by_where


def _cost(data: dict, units: list[dict], before: dict, strategy: str) -> tuple[list, set]:
    """(newly broken, newly fixed) for one strategy, against the current order."""
    after = _violations({**data, "units": renumbered(units, strategy)})
    broke = [(w, chars) for w, chars in after.items() if w not in before]
    fixed = {w for w in before if w not in after}
    return broke, fixed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Reorder units by level (reports first).")
    ap.add_argument("--strategy", choices=sorted(STRATEGIES), default="beginner-first",
                    help="beginner-first: generated HSK 1 units lead, nothing else "
                         "moves (default). level: full level order, which is far "
                         "more disruptive to already-generated content.")
    ap.add_argument("--apply", action="store_true",
                    help="write the new sort_order into content/units/")
    args = ap.parse_args(argv)

    data = curriculum_source.load()
    units = data.get("units", [])
    before = _violations(data)

    print(f"Out-of-scope sentences as things stand: {len(before)}\n")

    # Every cost below is measured against what is on disk *now*. If a reorder
    # has already been written and not yet regenerated, that baseline is the
    # broken one, and each strategy truthfully reports "nothing new would break"
    # — which reads as "this is free" and is the opposite of the truth.
    if len(before) > DIRTY_BASELINE:
        print(f"  ⚠ That is a lot. It usually means an ordering has already been")
        print(f"    applied and its content not yet regenerated, in which case every")
        print(f"    number below is measured against an already-broken curriculum.")
        print(f"    Restore first, then measure:  git checkout -- content/units/\n")

    print("What each ordering would cost:")
    for name in sorted(STRATEGIES):
        broke, fixed = _cost(data, units, before, name)
        mark = "→" if name == args.strategy else " "
        note = f"{len(broke):>4} would break"
        if fixed:
            note += f", {len(fixed)} would be fixed"
        print(f"  {mark} {name:<15} {note}")
    print()

    after_units = renumbered(units, args.strategy)
    broke, fixed = _cost(data, units, before, args.strategy)

    print(f"New order under '{args.strategy}' (first 20):")
    live = {u["id"] for u in units if u.get("status", "live") == "live"}
    for unit in after_units[:20]:
        kind = "generated" if unit.get("generated") else "curated"
        mark = " " if unit["id"] in live else "·"
        print(f"  {unit['sort_order']:>3}{mark} HSK {unit.get('hsk_level')} "
              f"{kind:<9} {unit.get('title')}")
    if len(after_units) > 20:
        print(f"  … and {len(after_units) - 20} more   (· = draft, not taught)")

    if broke:
        hit = sorted({w.split()[0] for w, _ in broke})
        print(f"\n✗ {len(broke)} sentence(s) in {len(hit)} lesson(s) would fall out of scope:")
        for where, chars in broke[:10]:
            print(f"    [{where}] → {' '.join(sorted(chars))}")
        if len(broke) > 10:
            print(f"    … and {len(broke) - 10} more")
        print(f"\n  Regenerate them afterwards, which is the point rather than the")
        print(f"  price: content written for a later position was written at the")
        print(f"  wrong level for this one.")
        print(f"    make generate-content ARGS=\"--level 1 --refresh\"")
    else:
        print("\n✓ Nothing falls out of scope.")

    if not args.apply:
        print("\n(report only) Re-run with ARGS=--apply to write this order.")
        return 0

    for unit in after_units:
        curriculum_source.write_unit(unit)
    curriculum_source.write_manifest(
        data.get("meta", {}), [u["id"] for u in after_units]
    )
    print(f"\n✓ rewrote sort_order on {len(after_units)} unit files (lessons untouched)")
    print("  Restart the app to pick it up — the database reloads on startup.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
