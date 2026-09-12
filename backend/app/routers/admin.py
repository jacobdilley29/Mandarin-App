"""Backup / export / restore endpoints (spec §7).

The manual export-import path exists so recovery never depends on the SQLite
file itself: Jacob can pull a JSON file off one machine and load it on another.

No auth, consistent with the rest of the app — Tailscale is the security
perimeter and this is a single-user instance on a private tailnet. The one
destructive operation (import) requires an explicit mode and takes its own
safety snapshot first.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .. import backup as backup_mod
from ..db import get_db

router = APIRouter(prefix="/api/admin", tags=["admin"])


class ImportRequest(BaseModel):
    # No default: a restore should never happen because a field was omitted.
    mode: Literal["merge", "replace"] = Field(
        description="'replace' wipes progress first (a true restore); "
        "'merge' upserts on top of what's there."
    )
    data: dict


@router.get("/backup-status")
def backup_status() -> dict:
    """Is the backup job actually producing files? Surfaced in the Me tab."""
    return backup_mod.last_backup_info()


@router.post("/backup")
def run_backup_now() -> dict:
    """Take a backup right now, in addition to the scheduled one."""
    try:
        return backup_mod.run_backup()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"backup failed: {exc}") from exc


@router.get("/export")
def export_progress(conn: sqlite3.Connection = Depends(get_db)) -> JSONResponse:
    """Download all progress data as JSON."""
    payload = backup_mod.export_progress(conn)
    stamp = payload["exported_at"].replace(":", "").replace("-", "")
    return JSONResponse(
        content=payload,
        headers={
            "Content-Disposition": f'attachment; filename="mandarin-progress-{stamp}.json"'
        },
    )


@router.post("/import")
def import_progress(
    req: ImportRequest, conn: sqlite3.Connection = Depends(get_db)
) -> dict:
    """Restore progress data from a JSON export."""
    try:
        counts = backup_mod.import_progress(req.data, mode=req.mode, conn=conn)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"mode": req.mode, "imported": counts, "total": sum(counts.values())}


@router.post("/import-file")
async def import_progress_file(
    mode: Literal["merge", "replace"] = "merge",
    file: UploadFile = File(...),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    """Same as /import, but takes the export file directly as an upload."""
    raw = await file.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"not valid JSON: {exc}") from exc
    try:
        counts = backup_mod.import_progress(payload, mode=mode, conn=conn)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"mode": mode, "imported": counts, "total": sum(counts.values())}
