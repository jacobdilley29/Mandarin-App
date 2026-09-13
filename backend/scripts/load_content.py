#!/usr/bin/env python3
"""Load content/curriculum.json into the SQLite DB (spec §5).

Runs the sentence↔vocab validator first and refuses to load content with
violations unless --force is given. Idempotent — safe to re-run.

Usage:
    python -m scripts.load_content            # validate + load
    python -m scripts.load_content --check    # validate only, don't load
    python -m scripts.load_content --force    # load even with violations
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as `python backend/scripts/load_content.py` too.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import content, curriculum_source, db  # noqa: E402
from app.config import REPO_ROOT  # noqa: E402
from app.validation import (  # noqa: E402
    allowed_chars,
    han_chars,
    placement_pool_chars,
    validate_curriculum,
    validate_grammar_prerequisites,
    validate_listen,
)


def split_violations_by_status(data: dict, violations: list) -> tuple[list, list]:
    """Split violations into (live, draft).

    A violation only matters where the learner can reach it. Draft units are
    gated out of Learn by design (spec §3.1), so a half-finished draft is
    reported and left alone rather than blocking the whole load — otherwise one
    unfinished generated lesson stops every *finished* unit from loading too.
    A violation in a live unit is still a refusal: that is what gets served.
    """
    draft_lessons = {
        lesson["id"]
        for unit in data.get("units", [])
        if curriculum_source.status_of(unit) != curriculum_source.STATUS_LIVE
        for lesson in unit.get("lessons", [])
    }
    live = [v for v in violations if v.where.split()[0] not in draft_lessons]
    draft = [v for v in violations if v.where.split()[0] in draft_lessons]
    return live, draft


def main() -> int:
    ap = argparse.ArgumentParser(description="Load curriculum content into SQLite.")
    ap.add_argument("--check", action="store_true", help="validate only")
    ap.add_argument("--force", action="store_true", help="load despite violations")
    ap.add_argument(
        "--path",
        default=None,
        help="load one combined curriculum file instead of content/units/*.json",
    )
    args = ap.parse_args()

    # Default: the per-unit source files (spec §3.1), merged into the combined
    # shape the validator and loader expect. --path still takes a single file so
    # a generated or experimental curriculum can be checked without installing it.
    if args.path:
        path = Path(args.path)
        if not path.is_file():
            print(f"✗ content file not found: {path}")
            return 2
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = curriculum_source.load()
        n_draft = sum(
            1 for u in data.get("units", [])
            if curriculum_source.status_of(u) != curriculum_source.STATUS_LIVE
        )
        n_live = len(data.get("units", [])) - n_draft
        print(f"Source: content/units/ — {n_live} live, {n_draft} draft")

    # The HSK 1 placement pool is pre-known (seeded as mastered on first run),
    # so lesson sentences may draw on its characters. Shared with the generator
    # via validation.placement_pool_chars() — two copies of this rule drifted
    # apart once already.
    result = validate_curriculum(data, extra_known_chars=placement_pool_chars())

    live_bad, draft_bad = split_violations_by_status(data, result.violations)

    if not result.violations:
        print("✓ curriculum validation passed — all sentences use in-scope characters")
    if draft_bad:
        print(f"• {len(draft_bad)} out-of-scope sentence(s) in DRAFT units — not loaded into Learn:")
        for v in draft_bad[:10]:
            print(f"    [{v.where}] {v.text}  → unknown: {' '.join(v.unknown)}")
        if len(draft_bad) > 10:
            print(f"    … and {len(draft_bad) - 10} more")
        print("  Re-run `make generate-content` to have those lessons rewritten in scope.")
    if live_bad:
        print(f"✗ {len(live_bad)} curriculum violation(s) in LIVE units:")
        for v in live_bad:
            print(f"    [{v.where}] {v.text}  → unknown: {' '.join(v.unknown)}")
        if not args.force and not args.check:
            print("Refusing to load. Fix the content or pass --force.")
            return 1

    # Grammar prerequisites: a lesson may not lean on a point taught later.
    gres = validate_grammar_prerequisites(data)
    if gres.ok:
        print("✓ grammar prerequisites resolve — no lesson reaches forward")
    else:
        print(f"✗ {len(gres.violations)} grammar prerequisite violation(s):")
        for v in gres.violations:
            print(f"    [{v.where}] {v.text}  → {' '.join(v.unknown)}")
        if not args.force and not args.check:
            print("Refusing to load. Fix the prerequisites or pass --force.")
            return 1

    # Validate listening comprehension sets against the full known-vocab pool.
    listen_path = REPO_ROOT / "content" / "listen.json"
    if listen_path.is_file():
        listen_data = json.loads(listen_path.read_text(encoding="utf-8"))
        words = [v["traditional"] for u in data.get("units", [])
                 for lesson in u.get("lessons", []) for v in lesson.get("vocab", [])]
        if content.HSK1_PATH.is_file():
            hsk1 = json.loads(content.HSK1_PATH.read_text(encoding="utf-8"))
            words += [v["traditional"] for v in hsk1.get("vocab", [])]
        allowed = allowed_chars(words, data.get("meta", {}).get("function_words", []))
        lres = validate_listen(listen_data, allowed)
        if lres.ok:
            print("✓ listen validation passed — comprehension sets use known vocab")
        else:
            print(f"✗ {len(lres.violations)} listen violation(s):")
            for v in lres.violations:
                print(f"    [{v.where}] {v.text}  → unknown: {' '.join(v.unknown)}")
            if not args.force and not args.check:
                print("Refusing to load. Fix content/listen.json or pass --force.")
                return 1

    if args.check:
        return 0 if (result.ok and gres.ok) else 1

    db.init_db()
    conn = db.connect()
    try:
        summary = content.load_curriculum(conn, data)
        hsk1 = content.load_hsk1_from_disk(conn)
        if hsk1:
            summary["hsk1_pool"] = hsk1
    finally:
        conn.close()
    print(f"✓ loaded: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
