#!/usr/bin/env python3
"""Curriculum coverage report (spec §3.1).

Prints what is being taught, what is staged as draft, and exactly which
completeness checks each draft still fails.

    python -m scripts.coverage           # summary + drafts
    python -m scripts.coverage --all     # every unit, including complete ones
    python -m scripts.coverage --json    # machine-readable
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import completeness, curriculum_source, sequence  # noqa: E402

GREEN, YELLOW, DIM, RESET = "\033[32m", "\033[33m", "\033[2m", "\033[0m"


def main() -> int:
    ap = argparse.ArgumentParser(description="Curriculum completeness report.")
    ap.add_argument("--all", action="store_true", help="list complete units too")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    data = curriculum_source.load()
    s = completeness.summary(data)
    seq = sequence.summary(data)

    if args.json:
        print(json.dumps({**s, "sequence": seq}, ensure_ascii=False, indent=2))
        return 0

    t = s["totals"]
    print(f"{s['units']} units — {GREEN}{s['live']} live{RESET}, {YELLOW}{s['draft']} draft{RESET}\n")
    print(f"  {'':<12} {'lessons':>8} {'vocab':>7} {'grammar':>8} {'sentences':>10} {'dialogue':>9}")
    for label in ("live", "draft", "all"):
        row = t[label]
        print(f"  {label:<12} {row['lessons']:>8} {row['vocab']:>7} {row['grammar']:>8} "
              f"{row['sentences']:>10} {row['dialogue_lines']:>9}")
    print()

    shown = [r for r in s["report"] if args.all or not r["complete"]]
    if not shown:
        print(f"{GREEN}✓ every unit is complete and live.{RESET}")
    for r in shown:
        mark = f"{GREEN}✓{RESET}" if r["complete"] else f"{YELLOW}○{RESET}"
        print(f"  {mark} {r['unit_id']:<12} {r['title']:<12} {r['status']}")
        for key in r["missing"]:
            print(f"      {YELLOW}missing{RESET}  {key:<20} {completeness.DESCRIPTIONS[key]}")
        for key in r["missing_optional"]:
            print(f"      {DIM}optional {key:<20} {completeness.DESCRIPTIONS[key]}{RESET}")

    # Sequencing, which is a different question from completeness: can the
    # learner actually read the live units, walking them in order? A unit can be
    # complete and still lean on a word only a draft teaches.
    print()
    if not seq["holes"]:
        print(f"{GREEN}✓ sequence is continuous — every live lesson reads from what came before.{RESET}")
    else:
        print(f"{YELLOW}○ {seq['holes']} untaught character(s) across "
              f"{seq['lessons_affected']} live lesson(s):{RESET}")
        for hole in sequence.holes(data)[:8]:
            print(f"      {hole.char}  [{hole.where}]  {DIM}{hole.reason}{RESET}")
        if seq["holes"] > 8:
            print(f"      {DIM}… and {seq['holes'] - 8} more{RESET}")
        if seq["waiting_on_drafts"]:
            print(f"  Fill these drafts to close it: {' '.join(seq['waiting_on_drafts'])}")
        if seq["taught_nowhere"]:
            print(f"  {YELLOW}Taught nowhere at all:{RESET} {' '.join(seq['taught_nowhere'])}")

    if s["draft"]:
        print(f"\n{YELLOW}{s['draft']} unit(s) are staged but not taught.{RESET}")
        print("Drafts never appear in Learn. Run generation to complete them:")
        print("  ANTHROPIC_API_KEY=... make generate-content")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
