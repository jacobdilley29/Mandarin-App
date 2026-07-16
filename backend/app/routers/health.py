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
        "phase": 1,
        "features": {
            # Talk tab degrades gracefully when no key is present.
            "conversation": settings.conversation_enabled,
            # Learn ships in Phase 1; the rest arrive in later phases.
            "learn": True,
            "review": False,
            "listen": False,
            "speak": False,
            "progress": False,
        },
        "whisper_model": settings.whisper_model,
    }
