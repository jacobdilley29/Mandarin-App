"""Health & capability reporting.

/api/health   — liveness
/api/status   — feature flags the frontend uses to enable/disable tabs
                (notably: conversation mode requires an Anthropic key).
"""

from __future__ import annotations

from fastapi import APIRouter

from .. import __version__
from ..config import get_settings

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@router.get("/status")
def status() -> dict:
    settings = get_settings()
    return {
        "version": __version__,
        "phase": 0,
        "features": {
            # Talk tab degrades gracefully when no key is present.
            "conversation": settings.conversation_enabled,
            # These arrive in later phases; surfaced now so the UI can label
            # tabs as "coming soon" honestly.
            "learn": False,
            "review": False,
            "listen": False,
            "speak": False,
            "progress": False,
        },
        "whisper_model": settings.whisper_model,
    }
