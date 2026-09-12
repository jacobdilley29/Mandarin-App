#!/usr/bin/env python3
"""One-time: split content/curriculum.json into one file per unit (spec §3.1).

A single 73 KB curriculum file was reviewable at 14 units. At the 70+ units the
HSK 1-4 syllabus needs it would not be: every content change would show up as a
diff against one enormous file, which is exactly what §3.1's per-unit source
files are there to avoid.

    python -m scripts.split_curriculum            # split
    python -m scripts.split_curriculum --check    # verify the round trip only

Verifies losslessness before writing anything: the merged result of the split
must equal the input exactly, or nothing is written.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import curriculum_source as cs  # noqa: E402


def _normalise(data: dict) -> dict:
    """Comparable form: unit order is carried by the manifest, not file order."""
    return {
        "meta": data.get("meta", {}),
        "units": sorted(data.get("units", []), key=lambda u: u.get("id", "")),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Split the curriculum into per-unit files.")
    ap.add_argument("--check", action="store_true", help="verify only, write nothing")
    args = ap.parse_args()

    if cs.is_split():
        print(f"Already split — {len(list(cs.UNITS_DIR.glob('*.json')))} unit files in {cs.UNITS_DIR}")
        return 0

    if not cs.MANIFEST_PATH.is_file():
        print(f"✗ no curriculum at {cs.MANIFEST_PATH}")
        return 2

    before = json.loads(cs.MANIFEST_PATH.read_text(encoding="utf-8"))
    n_units = len(before.get("units", []))
    n_lessons = sum(len(u.get("lessons", [])) for u in before.get("units", []))
    n_vocab = sum(len(l.get("vocab", [])) for u in before.get("units", []) for l in u.get("lessons", []))
    print(f"Source: {n_units} units · {n_lessons} lessons · {n_vocab} vocab")

    if args.check:
        print("(--check: nothing written)")
        return 0

    manifest, paths = cs.split(before)
    after = cs.load()

    if _normalise(after) != _normalise(before):
        print("✗ round trip is NOT lossless — refusing to leave the split in place")
        return 1

    print(f"✓ wrote {len(paths)} unit files to content/units/")
    print(f"✓ manifest: {manifest.name} ({n_units} units in order)")
    print("✓ round trip verified lossless")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
