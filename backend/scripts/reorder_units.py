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
    """Units in teaching order: by level, hand-authored first within each level.

    Authored-first within a level keeps 便利商店 opening HSK 2 and the other
    hand-polished units leading their own bands, while the beginner material
    that should come first actually does.
    """
    return sorted(
        units,
        key=lambda u: (
            u.get("hsk_level") or 0,
            1 if u.get("generated") else 0,
            u.get("sort_order", 0),
        ),
    )


def renumbered(units: list[dict]) -> list[dict]:
    out = []
    for i, unit in enumerate(level_order(units), start=1):
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Reorder units by level (reports first).")
    ap.add_argument("--apply", action="store_true",
                    help="write the new sort_order into content/units/")
    args = ap.parse_args(argv)

    data = curriculum_source.load()
    units = data.get("units", [])
    before = _violations(data)

    after_units = renumbered(units)
    after = _violations({**data, "units": after_units})

    new_breaks = {w: chars for w, chars in after.items() if w not in before}
    fixed = {w for w in before if w not in after}

    print("New order (first 20):")
    live = {u["id"] for u in units if u.get("status", "live") == "live"}
    for unit in after_units[:20]:
        kind = "generated" if unit.get("generated") else "curated"
        mark = " " if unit["id"] in live else "·"
        print(f"  {unit['sort_order']:>3}{mark} HSK {unit.get('hsk_level')} "
              f"{kind:<9} {unit.get('title')}")
    if len(after_units) > 20:
        print(f"  … and {len(after_units) - 20} more   (· = draft, not taught)")

    print(f"\nOut-of-scope sentences now      : {len(before)}")
    print(f"Out-of-scope sentences reordered : {len(after)}")

    if fixed:
        print(f"\n✓ {len(fixed)} would come back INTO scope")
    if new_breaks:
        print(f"\n✗ {len(new_breaks)} sentence(s) would fall OUT of scope:")
        for where, chars in list(new_breaks.items())[:15]:
            print(f"    [{where}] → {' '.join(sorted(chars))}")
        if len(new_breaks) > 15:
            print(f"    … and {len(new_breaks) - 15} more")
        print("\n  Each of those is a unit that would drop back to draft, and a")
        print("  regeneration call to bring back. Weigh that against the ordering.")
    elif not fixed:
        generated_with_content = sum(
            1 for u in units for l in u.get("lessons") or [] if l.get("sentences")
        )
        if generated_with_content:
            print("\n✓ Nothing changes scope — the reorder is free.")
        else:
            print("\n· No lesson content on disk yet, so there is nothing to put out")
            print("  of scope. Run this again once the units are generated.")

    if not args.apply:
        print("\n(report only) Re-run with ARGS=--apply to write the new order.")
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
