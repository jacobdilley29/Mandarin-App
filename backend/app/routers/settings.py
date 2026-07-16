"""Settings API — reads/writes the singleton settings row.

GET  /api/settings   — current settings
PUT  /api/settings   — partial update
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..db import get_db

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Columns the client is allowed to write, with light validation handled by the
# Pydantic model below.
_WRITABLE = {
    "show_pinyin",
    "playback_rate",
    "tts_voice",
    "theme",
    "daily_new_limit",
    "reduced_motion",
    "placement_done",
}

VOICES = ("zh-TW-HsiaoChenNeural", "zh-TW-YunJheNeural")
THEMES = ("system", "light", "dark")
RATES = (0.75, 1.0, 1.25)


class SettingsOut(BaseModel):
    show_pinyin: bool
    playback_rate: float
    tts_voice: str
    theme: str
    daily_new_limit: int
    reduced_motion: bool
    placement_done: bool


class SettingsUpdate(BaseModel):
    show_pinyin: bool | None = None
    playback_rate: float | None = None
    tts_voice: str | None = None
    theme: str | None = None
    daily_new_limit: int | None = Field(default=None, ge=0, le=100)
    reduced_motion: bool | None = None
    placement_done: bool | None = None


def _row_to_out(row: sqlite3.Row) -> SettingsOut:
    return SettingsOut(
        show_pinyin=bool(row["show_pinyin"]),
        playback_rate=row["playback_rate"],
        tts_voice=row["tts_voice"],
        theme=row["theme"],
        daily_new_limit=row["daily_new_limit"],
        reduced_motion=bool(row["reduced_motion"]),
        placement_done=bool(row["placement_done"]),
    )


def _fetch(conn: sqlite3.Connection) -> sqlite3.Row:
    conn.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
    conn.commit()
    row = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
    return row


@router.get("", response_model=SettingsOut)
def get_settings_endpoint(conn: sqlite3.Connection = Depends(get_db)) -> SettingsOut:
    return _row_to_out(_fetch(conn))


@router.put("", response_model=SettingsOut)
def update_settings_endpoint(
    patch: SettingsUpdate, conn: sqlite3.Connection = Depends(get_db)
) -> SettingsOut:
    data = patch.model_dump(exclude_none=True)

    # Domain validation beyond types.
    if "tts_voice" in data and data["tts_voice"] not in VOICES:
        raise HTTPException(422, f"tts_voice must be one of {VOICES}")
    if "theme" in data and data["theme"] not in THEMES:
        raise HTTPException(422, f"theme must be one of {THEMES}")
    if "playback_rate" in data and data["playback_rate"] not in RATES:
        raise HTTPException(422, f"playback_rate must be one of {RATES}")

    if data:
        cols = [c for c in data if c in _WRITABLE]
        assignments = ", ".join(f"{c} = ?" for c in cols)
        values = [int(data[c]) if isinstance(data[c], bool) else data[c] for c in cols]
        conn.execute(
            f"UPDATE settings SET {assignments}, updated_at = datetime('now') WHERE id = 1",
            values,
        )
        conn.commit()

    return _row_to_out(_fetch(conn))
