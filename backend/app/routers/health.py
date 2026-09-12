"""Health & capability reporting.

/api/health   — liveness
/api/status   — feature flags the frontend uses to enable/disable tabs
                (notably: conversation mode requires an Anthropic key).
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from .. import __version__, conversation
from ..config import get_settings
from ..db import get_db

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@router.get("/status")
def status(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    settings = get_settings()
    return {
        "version": __version__,
        "phase": 5,
        "features": {
            # Talk tab degrades gracefully when no key is present. The key may
            # come from .env or from the in-app setting stored in the DB.
            "conversation": conversation.available(conn),
            # The tutor needs the same key as Talk (spec §3.7 — the second and
            # only other networked call in the app).
            "tutor": conversation.available(conn),
            "learn": True,
            "review": True,
            "listen": True,
            "speak": True,
            "progress": True,
            # Backup/restore machinery (spec §7) is always available.
            "backups": True,
        },
        "whisper_model": settings.whisper_model,
    }
