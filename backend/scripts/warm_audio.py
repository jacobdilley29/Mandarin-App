#!/usr/bin/env python3
"""Pre-generate the TTS audio cache (spec §5 step 4).

"Pre-generate TTS audio for all vocab items and example sentences with edge-tts
(zh-TW voice) at build/seed time so lesson playback doesn't require live TTS
calls." Without this the first play of every clip waits on the network — on a
phone, mid-lesson, that is the difference between a lesson feeling instant and
feeling broken.

Only **live** units are warmed. Draft units are staged content nobody can reach
yet (see app/completeness.py), and synthesising a thousand clips for lessons
that aren't taught would cost minutes and tens of megabytes for nothing. When a
draft is promoted, re-run this.

Clips land in the same disk cache the /api/audio endpoint uses
(app/audio.py, keyed on voice+text), so warming and on-demand playback share
one cache and neither duplicates the other's work.

    python -m scripts.warm_audio                 # live units, default voice
    python -m scripts.warm_audio --dry-run       # count the work, synthesise nothing
    python -m scripts.warm_audio --both-voices   # both zh-TW voices
    python -m scripts.warm_audio --include-drafts

Resumable and idempotent: anything already cached is skipped, so an interrupted
run costs only what it hadn't reached.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import audio, curriculum_source  # noqa: E402
from app.config import get_settings  # noqa: E402


def clips(data: dict) -> list[tuple[str, str]]:
    """Every (text, kind) pair a lesson can play, de-duplicated in reading order."""
    seen: set[str] = set()
    out: list[tuple[str, str]] = []

    def add(text: str | None, kind: str) -> None:
        text = (text or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append((text, kind))

    for unit in sorted(data.get("units", []), key=lambda u: u.get("sort_order", 0)):
        for lesson in sorted(unit.get("lessons") or [], key=lambda l: l.get("sort_order", 0)):
            for v in lesson.get("vocab") or []:
                add(v.get("traditional"), "vocab")
                add((v.get("example") or {}).get("hanzi"), "example")
            for g in lesson.get("grammar") or []:
                for ex in g.get("examples") or []:
                    add(ex.get("hanzi"), "grammar")
            for s in lesson.get("sentences") or []:
                add("".join(s.get("tokens") or []), "sentence")
            for line in lesson.get("dialogue") or []:
                add(line.get("hanzi"), "dialogue")
    return out


async def warm(items: list[tuple[str, str]], voices: list[str], dry_run: bool) -> dict:
    stats = {"cached": 0, "made": 0, "failed": 0, "bytes": 0}
    total = len(items) * len(voices)
    done = 0

    for voice in voices:
        for text, _kind in items:
            done += 1
            path = audio.cache_path(text, voice)
            if path.is_file() and path.stat().st_size > 0:
                stats["cached"] += 1
                stats["bytes"] += path.stat().st_size
                continue
            if dry_run:
                stats["made"] += 1
                continue
            try:
                made = await audio.get_or_create(text, voice)
                stats["made"] += 1
                stats["bytes"] += made.stat().st_size
            except audio.TTSUnavailable as exc:
                stats["failed"] += 1
                if stats["failed"] <= 3:
                    print(f"  ! {text}: {exc}")
                if stats["failed"] >= 5 and stats["made"] == 0:
                    print("\n  Nothing is synthesising — the TTS service is unreachable.")
                    print("  Stopping rather than timing out once per clip.")
                    return stats
            if done % 50 == 0:
                print(f"  … {done}/{total}  ({stats['made']} made, {stats['cached']} cached)")
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Pre-generate the zh-TW audio cache.")
    ap.add_argument("--dry-run", action="store_true", help="count the work, synthesise nothing")
    ap.add_argument("--both-voices", action="store_true", help="warm both zh-TW voices")
    ap.add_argument("--include-drafts", action="store_true",
                    help="also warm units that aren't taught yet (slow, usually pointless)")
    ap.add_argument("--limit", type=int,
                    help="stop after this many clips — good for a first trial run")
    args = ap.parse_args()

    data = curriculum_source.load() if args.include_drafts else curriculum_source.load_live()
    items = clips(data)
    if args.limit:
        items = items[: args.limit]
    voices = sorted(audio.VOICES) if args.both_voices else [audio.DEFAULT_VOICE]

    n_units = len(data.get("units", []))
    scope = "all units" if args.include_drafts else "live units"
    print(f"{n_units} {scope} → {len(items)} distinct clips × {len(voices)} voice(s)")
    print(f"Cache: {get_settings().audio_dir}\n")

    stats = asyncio.run(warm(items, voices, args.dry_run))

    print()
    if args.dry_run:
        print(f"(--dry-run) {stats['cached']} already cached, {stats['made']} would be synthesised")
        return 0

    mb = stats["bytes"] / 1024 / 1024
    print(f"✓ {stats['made']} synthesised · {stats['cached']} already cached · {mb:.1f} MB total")
    if stats["failed"]:
        print(f"  {stats['failed']} clip(s) could not be generated (offline or blocked).")
        print("  Harmless: the app falls back to on-demand synthesis. Re-run when online.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
