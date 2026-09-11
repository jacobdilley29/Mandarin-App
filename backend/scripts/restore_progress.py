#!/usr/bin/env python3
"""Copy learner progress from a backup database into the live one.

Content and progress live in the same SQLite file, so rebuilding content by
starting from a fresh database throws away streaks, SRS scheduling and lesson
completion along with it. This moves the progress back.

Only progress tables are touched — units, lessons, vocab and grammar are left
exactly as the live database has them. Rows referring to content that no longer
exists (a card for an imported word that has since been reverted, progress for a
lesson that no longer exists) are dropped rather than restored, because they
would otherwise sit in the deck pointing at nothing.

Restored: lesson_progress, srs_cards (+ review_log), daily_activity,
drill_errors, tone_attempts, talk_sessions, talk_messages, and the settings row
(including the in-app Anthropic key).

Usage:
    python -m scripts.restore_progress --from ../data/mandarin.db.bak-20260911-1830
    python -m scripts.restore_progress --from BACKUP --dry-run

Safe to re-run: rows already present in the live database are left alone.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db  # noqa: E402

# Settings columns that are the learner's, as opposed to schema bookkeeping.
_SETTINGS_COLS = (
    "show_pinyin", "phonetic", "playback_rate", "tts_voice", "theme",
    "daily_new_limit", "reduced_motion", "placement_done", "anthropic_api_key",
)


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _shared_columns(src: sqlite3.Connection, dst: sqlite3.Connection, table: str) -> list[str]:
    """Columns present in both, so a backup from an older schema still restores."""
    return [c for c in _columns(src, table) if c in set(_columns(dst, table))]


def _ids(conn: sqlite3.Connection, table: str, col: str = "id") -> set[str]:
    return {r[col] for r in conn.execute(f"SELECT {col} FROM {table}").fetchall()}


def restore(src: sqlite3.Connection, dst: sqlite3.Connection, dry_run: bool) -> dict:
    report: dict[str, dict[str, int]] = {}

    live_lessons = _ids(dst, "lessons")
    live_vocab = _ids(dst, "vocab")
    live_grammar = _ids(dst, "grammar")

    def copy(table: str, keep, key_cols: list[str]) -> None:
        """Copy rows `keep` accepts, skipping ones the live DB already has."""
        cols = _shared_columns(src, dst, table)
        if not cols:
            report[table] = {"restored": 0, "skipped": 0, "dropped": 0}
            return
        existing = {
            tuple(r[c] for c in key_cols)
            for r in dst.execute(f"SELECT {','.join(key_cols)} FROM {table}").fetchall()
        }
        restored = skipped = dropped = 0
        placeholders = ",".join("?" * len(cols))
        for row in src.execute(f"SELECT {','.join(cols)} FROM {table}").fetchall():
            data = {c: row[c] for c in cols}
            if not keep(data):
                dropped += 1
                continue
            if tuple(data[c] for c in key_cols) in existing:
                skipped += 1
                continue
            if not dry_run:
                dst.execute(
                    f"INSERT INTO {table} ({','.join(cols)}) VALUES ({placeholders})",
                    [data[c] for c in cols],
                )
            restored += 1
        report[table] = {"restored": restored, "skipped": skipped, "dropped": dropped}

    # --- Lesson completion: only for lessons that still exist ---
    copy("lesson_progress", lambda r: r["lesson_id"] in live_lessons, ["lesson_id"])

    # --- SRS cards: only for content that still exists ---
    def card_is_live(r: dict) -> bool:
        if r["item_type"] == "vocab":
            return r["item_id"] in live_vocab
        if r["item_type"] == "grammar":
            return r["item_id"] in live_grammar
        return False

    card_cols = _shared_columns(src, dst, "srs_cards")
    id_map: dict[int, int] = {}
    kept = dropped = 0
    insert_cols = [c for c in card_cols if c != "id"]
    existing_cards = {
        (r["item_type"], r["item_id"], r["card_type"])
        for r in dst.execute("SELECT item_type,item_id,card_type FROM srs_cards").fetchall()
    }
    for row in src.execute(f"SELECT {','.join(card_cols)} FROM srs_cards").fetchall():
        data = {c: row[c] for c in card_cols}
        if not card_is_live(data):
            dropped += 1
            continue
        key = (data["item_type"], data["item_id"], data["card_type"])
        if key in existing_cards:
            continue
        if dry_run:
            kept += 1
            continue
        cur = dst.execute(
            f"INSERT INTO srs_cards ({','.join(insert_cols)}) "
            f"VALUES ({','.join('?' * len(insert_cols))})",
            [data[c] for c in insert_cols],
        )
        id_map[data["id"]] = int(cur.lastrowid)
        kept += 1
    report["srs_cards"] = {"restored": kept, "skipped": 0, "dropped": dropped}

    # --- Review log: follows its card's new id ---
    log_cols = [c for c in _shared_columns(src, dst, "review_log") if c != "id"]
    logs = 0
    if not dry_run and id_map:
        for row in src.execute(f"SELECT {','.join(log_cols)} FROM review_log").fetchall():
            data = {c: row[c] for c in log_cols}
            new_card = id_map.get(data["card_id"])
            if new_card is None:
                continue
            data["card_id"] = new_card
            dst.execute(
                f"INSERT INTO review_log ({','.join(log_cols)}) "
                f"VALUES ({','.join('?' * len(log_cols))})",
                [data[c] for c in log_cols],
            )
            logs += 1
    report["review_log"] = {"restored": logs, "skipped": 0, "dropped": 0}

    # --- Streak, error logs, conversations: no content dependency ---
    copy("daily_activity", lambda r: True, ["day"])
    copy("drill_errors", lambda r: True, ["id"])
    copy("tone_attempts", lambda r: True, ["id"])
    copy("talk_sessions", lambda r: True, ["id"])
    copy("talk_messages", lambda r: True, ["id"])

    # --- Settings: the learner's preferences and in-app API key ---
    cols = [c for c in _SETTINGS_COLS if c in set(_shared_columns(src, dst, "settings"))]
    changed = 0
    old = src.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    if old and cols:
        if not dry_run:
            dst.execute(
                f"UPDATE settings SET {','.join(f'{c}=?' for c in cols)}, "
                "updated_at = datetime('now') WHERE id = 1",
                [old[c] for c in cols],
            )
        changed = len(cols)
    report["settings"] = {"restored": changed, "skipped": 0, "dropped": 0}
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Restore progress from a backup DB.")
    ap.add_argument("--from", dest="source", required=True, help="path to the backup .db")
    ap.add_argument("--dry-run", action="store_true", help="report without writing")
    args = ap.parse_args()

    source = Path(args.source).expanduser()
    if not source.is_file():
        raise SystemExit(f"✗ no such file: {source}")

    db.init_db()
    dst = db.connect()
    src = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    try:
        report = restore(src, dst, args.dry_run)
        if not args.dry_run:
            dst.commit()
    finally:
        src.close()
        dst.close()

    print(f"{'Would restore' if args.dry_run else 'Restored'} from {source.name}:\n")
    width = max(len(t) for t in report)
    for table, counts in report.items():
        bits = [f"{counts['restored']:>5} restored"]
        if counts["skipped"]:
            bits.append(f"{counts['skipped']} already present")
        if counts["dropped"]:
            bits.append(f"{counts['dropped']} dropped (content no longer exists)")
        print(f"  {table:<{width}}  {' · '.join(bits)}")
    if args.dry_run:
        print("\n(dry run — nothing written)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
