"""Audio API — cached zh-TW TTS.

GET /api/audio?text=...&voice=...   returns audio/mpeg (cached on disk)

Returns 503 when a clip can't be synthesised (e.g. offline). The frontend
treats that as "audio unavailable" and degrades gracefully rather than breaking
the exercise.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from .. import audio

router = APIRouter(prefix="/api", tags=["audio"])


@router.get("/audio")
async def get_audio(
    text: str = Query(..., min_length=1, max_length=400),
    voice: str | None = Query(default=None),
) -> FileResponse:
    try:
        path = await audio.get_or_create(text, voice)
    except audio.TTSUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))
    return FileResponse(
        path,
        media_type="audio/mpeg",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
