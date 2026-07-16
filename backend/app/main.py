"""台灣華語老師 — FastAPI application.

One process, one port. Serves the JSON API under /api and, in production, the
built Vite frontend (frontend/dist) as a single-page app. During development
you run Vite separately (it proxies /api here), so a missing dist/ is fine.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, content
from .config import get_settings
from .db import connect, init_db
from .routers import (
    audio,
    health,
    learn,
    listen,
    progress,
    review,
    speak,
    talk,
    settings as settings_router,
)

settings = get_settings()

app = FastAPI(
    title="台灣華語老師 — Taiwanese Mandarin Teacher",
    version=__version__,
    description="Local, self-hosted app for learning Taiwanese Mandarin.",
)

# In dev, Vite runs on its own port; allow it to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    settings.ensure_dirs()
    init_db()
    # Seed curriculum content on first run if the tables are empty.
    conn = connect()
    try:
        content.ensure_loaded(conn)
    finally:
        conn.close()


# --- API routers ---
app.include_router(health.router)
app.include_router(settings_router.router)
app.include_router(learn.router)
app.include_router(review.router)
app.include_router(listen.router)
app.include_router(speak.router)
app.include_router(talk.router)
app.include_router(progress.router)
app.include_router(audio.router)


# --- Cached TTS audio (populated in Phase 1); harmless to expose now ---
settings.ensure_dirs()
app.mount("/audio", StaticFiles(directory=str(settings.audio_dir)), name="audio")


# --- Frontend (built SPA) ---
_dist: Path = settings.frontend_dist


def _mount_frontend() -> None:
    """Serve the built SPA with history-fallback, if it exists.

    Registered last so it never shadows /api or /audio. If the frontend hasn't
    been built yet, we serve a friendly placeholder at / instead of 404-ing.
    """
    assets = _dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):  # noqa: ANN202
        # Never let the catch-all swallow the API namespace.
        if full_path.startswith(("api/", "audio/")):
            return JSONResponse({"detail": "Not Found"}, status_code=404)

        index = _dist / "index.html"
        if index.is_file():
            candidate = (_dist / full_path).resolve()
            # Serve a real static file if the path points at one (within dist).
            if (
                full_path
                and _dist.resolve() in candidate.parents
                and candidate.is_file()
            ):
                return FileResponse(candidate)
            return FileResponse(index)  # history fallback

        return JSONResponse(
            {
                "detail": "Frontend not built yet.",
                "hint": "Run `make build-frontend` (or `cd frontend && npm run build`), "
                "then reload. In development run `npm run dev` in frontend/ instead.",
            },
            status_code=200,
        )


_mount_frontend()


def run() -> None:
    """Entry point used by `python -m app` / the Makefile."""
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
    )


if __name__ == "__main__":
    run()
