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
    validate_curriculum,
    validate_listen,
)


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
    # so lesson sentences may draw on its characters. Feed them to the validator
    # as always-known, mirroring the learner's real starting point.
    hsk1_chars: set[str] = set()
    if content.HSK1_PATH.is_file():
        hsk1 = json.loads(content.HSK1_PATH.read_text(encoding="utf-8"))
        for v in hsk1.get("vocab", []):
            hsk1_chars |= han_chars(v["traditional"])

    result = validate_curriculum(data, extra_known_chars=hsk1_chars)
    if result.ok:
        print("✓ curriculum validation passed — all sentences use in-scope characters")
    else:
        print(f"✗ {len(result.violations)} curriculum violation(s):")
        for v in result.violations:
            print(f"    [{v.where}] {v.text}  → unknown: {' '.join(v.unknown)}")
        if not args.force and not args.check:
            print("Refusing to load. Fix the content or pass --force.")
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
        return 0 if result.ok else 1

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
