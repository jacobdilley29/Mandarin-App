"""Backup, export/import, retention and the legacy-DB split (spec §7).

These are the tests that matter most in this codebase: the app was lost once
because nothing here existed. A restore that silently drops a table would be
indistinguishable from the original failure.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app import backup
from app.config import Settings
from app.db import CONTENT_TABLES, PROGRESS_TABLES

from .conftest import CONTENT_SCHEMA, PROGRESS_SCHEMA, attached_conn


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Point the whole app at a throwaway data directory."""
    d = tmp_path / "data"
    d.mkdir()
    settings = Settings(data_dir=d)
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    monkeypatch.setattr("app.backup.get_settings", lambda: settings)
    settings.ensure_dirs()

    # A progress.db with something worth losing in it.
    conn = sqlite3.connect(settings.progress_db_path)
    conn.executescript(PROGRESS_SCHEMA)
    conn.execute(
        """INSERT INTO srs_cards (item_type, item_id, card_type, stability,
                                  difficulty, due, reps, lapses, state)
           VALUES ('vocab', 'v_bianli', 'recognition', 12.5, 6.25,
                   '2026-10-01T09:00:00+00:00', 7, 2, 'review')"""
    )
    conn.execute("INSERT INTO review_log (card_id, rating, elapsed_ms) VALUES (1, 3, 4200)")
    conn.execute(
        "INSERT INTO lesson_progress (lesson_id, completed, best_score, unlocked) "
        "VALUES ('l_conv_1', 1, 0.93, 1)"
    )
    conn.execute("INSERT INTO tone_attempts (target_text, correct, total) VALUES ('謝謝', 2, 2)")
    conn.execute("INSERT INTO daily_activity (day, minutes, reviews_done) VALUES ('2026-09-12', 18.5, 40)")
    conn.execute("UPDATE settings SET daily_new_limit = 22, placement_done = 1, theme = 'dark'")
    conn.commit()
    conn.close()

    # A content.db too, so nothing under test confuses "absent" with "empty".
    c = sqlite3.connect(settings.content_db_path)
    c.executescript(CONTENT_SCHEMA)
    c.execute("INSERT INTO vocab (id, traditional, pinyin, gloss) VALUES ('v_bianli', '便利', 'biànlì', 'convenient')")
    c.commit()
    c.close()

    return settings


# ---------------------------------------------------------------------------
# The schema lists in db.py drive migration and export; if they drift out of
# step with the .sql files, data goes missing silently. Pin them.
# ---------------------------------------------------------------------------
def _tables_in(schema_sql: str) -> set[str]:
    return set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", schema_sql))


def test_progress_tables_match_the_schema():
    declared = _tables_in(PROGRESS_SCHEMA) - {"progress_meta"}
    assert declared == set(PROGRESS_TABLES)


def test_content_tables_match_the_schema():
    declared = _tables_in(CONTENT_SCHEMA) - {"schema_meta"}
    assert declared == set(CONTENT_TABLES)


def test_the_two_schemas_share_no_table_names():
    """A shared name would be shadowed by main once both are ATTACHed."""
    assert not _tables_in(CONTENT_SCHEMA) & _tables_in(PROGRESS_SCHEMA)


# ---------------------------------------------------------------------------
# Export / import round trip
# ---------------------------------------------------------------------------
def test_export_contains_every_progress_table(data_dir):
    payload = backup.export_progress()
    assert set(payload["tables"]) == set(PROGRESS_TABLES)
    assert payload["format"] == backup.EXPORT_FORMAT
    assert payload["exported_at"]


def test_replace_round_trip_restores_state_exactly(data_dir):
    before = backup.export_progress()

    # Lose everything.
    data_dir.progress_db_path.unlink()
    conn = sqlite3.connect(data_dir.progress_db_path)
    conn.executescript(PROGRESS_SCHEMA)
    conn.commit()
    conn.close()
    assert backup.export_progress()["tables"]["srs_cards"] == []

    backup.import_progress(before, mode="replace")

    after = backup.export_progress()
    for table in PROGRESS_TABLES:
        assert after["tables"][table] == before["tables"][table], table


def test_srs_scheduling_state_survives_a_round_trip(data_dir):
    """Floats and timestamps are what FSRS actually needs back."""
    before = backup.export_progress()
    backup.import_progress(before, mode="replace")
    card = backup.export_progress()["tables"]["srs_cards"][0]

    assert card["stability"] == 12.5
    assert card["difficulty"] == 6.25
    assert card["due"] == "2026-10-01T09:00:00+00:00"
    assert (card["reps"], card["lapses"], card["state"]) == (7, 2, "review")


def test_replace_clears_rows_absent_from_the_payload(data_dir):
    payload = backup.export_progress()
    payload["tables"]["tone_attempts"] = []

    backup.import_progress(payload, mode="replace")

    assert backup.export_progress()["tables"]["tone_attempts"] == []


def test_merge_keeps_rows_absent_from_the_payload(data_dir):
    payload = backup.export_progress()
    payload["tables"]["tone_attempts"] = []

    backup.import_progress(payload, mode="merge")

    assert len(backup.export_progress()["tables"]["tone_attempts"]) == 1


def test_import_always_leaves_a_settings_row(data_dir):
    payload = backup.export_progress()
    payload["tables"]["settings"] = []

    backup.import_progress(payload, mode="replace")

    rows = backup.export_progress()["tables"]["settings"]
    assert len(rows) == 1 and rows[0]["id"] == 1


def test_import_takes_a_safety_snapshot_first(data_dir):
    backup.import_progress(backup.export_progress(), mode="replace")
    assert list(data_dir.backup_dir.glob("progress-*-pre-import.db"))


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"format": 99, "tables": {}}, "unsupported export format"),
        ({"format": 1}, "no 'tables' object"),
        ({"format": 1, "tables": {"vocab": []}}, "unknown tables"),
    ],
)
def test_malformed_exports_are_rejected_before_anything_is_written(data_dir, payload, message):
    with pytest.raises(ValueError, match=message):
        backup.import_progress(payload, mode="replace", safety_backup=False)
    # The real data is still there.
    assert len(backup.export_progress()["tables"]["srs_cards"]) == 1


def test_unknown_mode_is_rejected(data_dir):
    with pytest.raises(ValueError, match="unknown import mode"):
        backup.import_progress(backup.export_progress(), mode="overwrite")


# ---------------------------------------------------------------------------
# Snapshots, the nightly job, retention
# ---------------------------------------------------------------------------
def test_snapshot_is_a_readable_database_with_the_data_in_it(data_dir):
    snap = backup.snapshot_progress()

    conn = sqlite3.connect(snap)
    assert conn.execute("SELECT COUNT(*) FROM srs_cards").fetchone()[0] == 1
    assert conn.execute("SELECT daily_new_limit FROM settings").fetchone()[0] == 22
    conn.close()


def test_run_backup_writes_both_a_snapshot_and_an_export(data_dir):
    result = backup.run_backup()

    assert Path(result["snapshot"]).is_file()
    export = Path(result["export"])
    assert export.is_file()

    import gzip

    with gzip.open(export, "rt", encoding="utf-8") as fh:
        payload = json.load(fh)
    assert len(payload["tables"]["srs_cards"]) == 1


def test_prune_removes_old_backups_but_keeps_the_newest(data_dir):
    old = datetime.now() - timedelta(days=90)
    stamps = [(old + timedelta(days=i)).strftime("%Y%m%d-%H%M%S") for i in range(4)]
    for stamp in stamps:
        path = data_dir.backup_dir / f"progress-{stamp}.db"
        path.write_bytes(b"x")
        age = time.time() - 90 * 86400
        import os

        os.utime(path, (age, age))

    removed = backup.prune(retention_days=30)

    survivors = sorted(p.name for p in data_dir.backup_dir.glob("progress-*.db"))
    assert len(removed) == 3
    assert survivors == [f"progress-{stamps[-1]}.db"], "the newest must always survive"


def test_prune_ignores_files_that_are_not_backups(data_dir):
    stray = data_dir.backup_dir / "progress-notes.db"
    stray.write_bytes(b"x")
    import os

    os.utime(stray, (0, 0))

    backup.prune(retention_days=1)

    assert stray.exists()


def test_recent_backups_are_not_pruned(data_dir):
    backup.run_backup()
    backup.run_backup()

    assert backup.prune(retention_days=30) == []


def test_backup_status_reports_no_backup_before_any_runs(data_dir):
    info = backup.last_backup_info()
    assert info["last_backup_at"] is None
    assert info["snapshot_count"] == 0


def test_backup_status_reports_the_latest_backup(data_dir):
    backup.run_backup()

    info = backup.last_backup_info()
    assert info["snapshot_count"] == 1
    assert info["export_count"] == 1
    assert info["last_backup_at"] is not None
    assert info["retention_days"] == 30
    assert info["total_bytes"] > 0


# ---------------------------------------------------------------------------
# The one-time split of a pre-existing single-file database
# ---------------------------------------------------------------------------
@pytest.fixture
def legacy_data_dir(tmp_path, monkeypatch):
    """A data dir holding only the old combined mandarin.db."""
    d = tmp_path / "data"
    d.mkdir()
    settings = Settings(data_dir=d)
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    monkeypatch.setattr("app.backup.get_settings", lambda: settings)
    monkeypatch.setattr("app.migrate.get_settings", lambda: settings)

    conn = sqlite3.connect(settings.legacy_db_path)
    conn.executescript(CONTENT_SCHEMA)
    conn.executescript(PROGRESS_SCHEMA)
    conn.execute("INSERT INTO units (id, title) VALUES ('u_conv', '便利商店')")
    conn.execute("INSERT INTO lessons (id, unit_id, title) VALUES ('l_conv_1', 'u_conv', 'Lesson 1')")
    conn.execute("INSERT INTO vocab (id, traditional, pinyin, gloss) VALUES ('v_bianli', '便利', 'biànlì', 'convenient')")
    conn.execute(
        "INSERT INTO srs_cards (item_type, item_id, card_type, stability, reps, state) "
        "VALUES ('vocab', 'v_bianli', 'recognition', 9.75, 4, 'review')"
    )
    conn.execute("INSERT INTO lesson_progress (lesson_id, completed, best_score) VALUES ('l_conv_1', 1, 0.88)")
    conn.execute("UPDATE settings SET daily_new_limit = 31")
    conn.commit()
    conn.close()
    return settings


def test_legacy_split_routes_each_table_to_the_right_file(legacy_data_dir):
    from app.migrate import split_legacy_db

    counts = split_legacy_db()

    assert counts["vocab"] == 1 and counts["srs_cards"] == 1

    content = sqlite3.connect(legacy_data_dir.content_db_path)
    assert content.execute("SELECT COUNT(*) FROM units").fetchone()[0] == 1
    assert content.execute("SELECT COUNT(*) FROM lessons").fetchone()[0] == 1
    # Progress tables must not exist in the content file at all.
    names = {r[0] for r in content.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "srs_cards" not in names
    content.close()

    progress = sqlite3.connect(legacy_data_dir.progress_db_path)
    assert progress.execute("SELECT stability FROM srs_cards").fetchone()[0] == 9.75
    assert progress.execute("SELECT best_score FROM lesson_progress").fetchone()[0] == 0.88
    names = {r[0] for r in progress.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "vocab" not in names
    progress.close()


def test_legacy_split_preserves_the_users_settings_row(legacy_data_dir):
    from app.migrate import split_legacy_db

    split_legacy_db()

    conn = sqlite3.connect(legacy_data_dir.progress_db_path)
    rows = conn.execute("SELECT id, daily_new_limit FROM settings").fetchall()
    conn.close()
    assert rows == [(1, 31)], "the learner's settings must win over the seeded default"


def test_legacy_split_keeps_the_original_file(legacy_data_dir):
    from app.migrate import split_legacy_db

    split_legacy_db()

    assert not legacy_data_dir.legacy_db_path.exists()
    assert legacy_data_dir.legacy_db_path.with_name("mandarin.db.pre-split.bak").is_file()


def test_legacy_split_is_a_no_op_the_second_time(legacy_data_dir):
    from app.migrate import split_legacy_db

    split_legacy_db()
    assert split_legacy_db() is None


def test_split_refuses_to_overwrite_an_existing_split(legacy_data_dir):
    """A stray legacy file must never clobber live databases."""
    from app.migrate import split_legacy_db

    sqlite3.connect(legacy_data_dir.progress_db_path).close()

    assert split_legacy_db() is None
    assert legacy_data_dir.legacy_db_path.exists(), "left in place for the user to deal with"


# ---------------------------------------------------------------------------
# The ATTACH layout itself
# ---------------------------------------------------------------------------
def test_queries_join_across_the_two_databases(tmp_path):
    """The cross-file joins the app relies on (e.g. progress.py) still work."""
    conn = attached_conn(tmp_path)
    conn.execute("INSERT INTO vocab (id, traditional, pinyin, gloss) VALUES ('v1', '水', 'shuǐ', 'water')")
    conn.execute(
        "INSERT INTO srs_cards (item_type, item_id, card_type, state) VALUES ('vocab', 'v1', 'recognition', 'review')"
    )
    conn.commit()

    row = conn.execute(
        """SELECT v.traditional, c.state
           FROM srs_cards c JOIN vocab v ON v.id = c.item_id
           WHERE c.item_type = 'vocab'"""
    ).fetchone()
    conn.close()

    assert tuple(row) == ("水", "review")


def test_wiping_content_leaves_progress_intact(tmp_path):
    """The whole reason for the split: a content reseed must not cascade."""
    conn = attached_conn(tmp_path)
    conn.execute("INSERT INTO units (id, title) VALUES ('u1', 'U')")
    conn.execute("INSERT INTO lessons (id, unit_id, title) VALUES ('l1', 'u1', 'x')")
    conn.execute("INSERT INTO lesson_progress (lesson_id, completed) VALUES ('l1', 1)")
    conn.commit()

    conn.execute("DELETE FROM lessons")
    conn.execute("DELETE FROM units")
    conn.commit()

    assert conn.execute("SELECT completed FROM lesson_progress WHERE lesson_id = 'l1'").fetchone()[0] == 1
    conn.close()
