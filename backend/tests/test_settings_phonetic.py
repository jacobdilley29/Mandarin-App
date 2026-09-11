"""Tests for the phonetic (pinyin/zhuyin) setting and its migration."""

from __future__ import annotations

import sqlite3
import subprocess
from pathlib import Path

import pytest

from app import content, db
from app.routers.settings import PHONETIC

REPO = Path(__file__).resolve().parents[2]


def _put(conn: sqlite3.Connection, **patch):
    """Apply a settings patch the way the PUT endpoint does."""
    from app.routers.settings import SettingsUpdate, update_settings_endpoint

    return update_settings_endpoint(SettingsUpdate(**patch), conn)


def test_default_is_pinyin(conn):
    row = conn.execute("SELECT phonetic, show_pinyin FROM settings WHERE id = 1").fetchone()
    assert row["phonetic"] == "pinyin"
    assert row["show_pinyin"] == 1


@pytest.mark.parametrize("mode", PHONETIC)
def test_every_mode_round_trips(conn, mode):
    assert _put(conn, phonetic=mode).phonetic == mode


def test_unknown_mode_is_rejected(conn):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        _put(conn, phonetic="klingon")
    assert e.value.status_code == 422


def test_legacy_show_pinyin_stays_in_sync(conn):
    # Setting a notation implies the annotation is on; "off" implies it is not.
    assert _put(conn, phonetic="zhuyin").show_pinyin is True
    assert _put(conn, phonetic="off").show_pinyin is False

    # An old client writing show_pinyin still gets a coherent phonetic value.
    out = _put(conn, show_pinyin=True)
    assert out.phonetic == "pinyin" and out.show_pinyin is True
    out = _put(conn, show_pinyin=False)
    assert out.phonetic == "off" and out.show_pinyin is False


def test_show_pinyin_true_preserves_a_chosen_notation(conn):
    """Re-enabling the annotation must not silently demote zhuyin to pinyin."""
    _put(conn, phonetic="zhuyin")
    _put(conn, phonetic="off")
    # ...user turns it back on through the legacy flag.
    assert _put(conn, show_pinyin=True).phonetic == "pinyin"
    # ...but toggling off and on while on zhuyin keeps zhuyin.
    _put(conn, phonetic="zhuyin")
    assert _put(conn, show_pinyin=True).phonetic == "zhuyin"


def test_migrates_a_database_created_before_the_column_existed(tmp_path, monkeypatch):
    """An existing user's DB must gain the column and keep their preference."""
    old_schema = subprocess.run(
        ["git", "show", "HEAD:backend/app/schema.sql"],
        capture_output=True, text=True, cwd=REPO, check=True,
    ).stdout
    import re
    if re.search(r"^\s*phonetic\s+TEXT", old_schema, re.M):
        pytest.skip("HEAD already contains the phonetic column")

    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app import config
    config.get_settings.cache_clear()

    path = tmp_path / "mandarin.db"
    c = sqlite3.connect(path)
    c.executescript(old_schema)
    c.execute("UPDATE settings SET show_pinyin = 0")   # user had pinyin hidden
    c.commit()
    c.close()

    db.init_db()
    db.init_db()   # idempotent

    c = db.connect()
    assert "phonetic" in {r["name"] for r in c.execute("PRAGMA table_info(settings)")}
    assert "example_zhuyin" in {r["name"] for r in c.execute("PRAGMA table_info(vocab)")}
    # The hidden-pinyin preference carries over rather than resetting to on.
    assert c.execute("SELECT phonetic FROM settings").fetchone()["phonetic"] == "off"
    c.close()
    config.get_settings.cache_clear()


def test_loading_content_populates_zhuyin(conn):
    content.load_curriculum(conn, {
        "units": [{
            "id": "u1", "title": "U", "hsk_level": 2, "sort_order": 1,
            "lessons": [{
                "id": "l1", "title": "L", "sort_order": 1,
                "vocab": [{
                    "id": "vz", "traditional": "便利商店", "pinyin": "biànlì shāngdiàn",
                    "gloss": "convenience store",
                    "example": {"hanzi": "那是便利商店。",
                                "pinyin": "Nà shì biànlì shāngdiàn。", "gloss": "That's one."},
                }],
                "sentences": [{"tokens": ["我", "要", "水"], "pinyin": "Wǒ yào shuǐ。",
                               "gloss": "I want water.", "cloze_index": 2}],
                "dialogue": [{"speaker": "A", "hanzi": "你好", "pinyin": "Nǐ hǎo", "gloss": "Hi"}],
            }],
        }],
    })
    row = conn.execute("SELECT zhuyin, example_zhuyin FROM vocab WHERE id = 'vz'").fetchone()
    assert row["zhuyin"] == "ㄅㄧㄢˋ ㄌㄧˋ ㄕㄤ ㄉㄧㄢˋ"
    assert row["example_zhuyin"].startswith("ㄋㄚˋ ㄕˋ")

    import json
    lesson = conn.execute("SELECT sentences, dialogue FROM lessons WHERE id = 'l1'").fetchone()
    assert json.loads(lesson["sentences"])[0]["zhuyin"] == "ㄨㄛˇ ㄧㄠˋ ㄕㄨㄟˇ。"
    assert json.loads(lesson["dialogue"])[0]["zhuyin"] == "ㄋㄧˇ ㄏㄠˇ"
