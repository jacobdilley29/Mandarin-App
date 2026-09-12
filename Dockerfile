# 台灣華語老師 — one image, two roles (app server + backup cron).
#
# Nothing mutable lives in this image. The SQLite databases, the TTS audio cache
# and the backups all sit on the named volume mounted at /data, so rebuilding
# or replacing the image cannot touch learner progress (spec §7).

# ---------------------------------------------------------------------------
# Stage 1 — build the Vite frontend
# ---------------------------------------------------------------------------
FROM node:20-alpine AS frontend

WORKDIR /build
# Copy manifests first so the dependency layer caches across source edits.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


# ---------------------------------------------------------------------------
# Stage 2 — runtime
# ---------------------------------------------------------------------------
FROM python:3.11-slim AS runtime

# cron drives the nightly backup in the `backup` service; tini reaps zombies so
# uvicorn and cron both stop cleanly on `docker compose down`.
RUN apt-get update \
    && apt-get install -y --no-install-recommends cron tini curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/data

WORKDIR /app

COPY backend/requirements.txt backend/requirements-accel.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

# Optional accelerators, best-effort. praat-parselmouth publishes no Linux arm64
# wheel, so on an Apple Silicon Mac this step finds nothing to install — the app
# then uses the numpy pitch tracker (pitch.py falls back on its own). Without
# --only-binary pip would try to COMPILE Praat here and fail the whole build,
# which is exactly what it used to do.
RUN pip install --no-cache-dir --only-binary=:all: -r backend/requirements-accel.txt \
    || echo "NOTE: optional accelerators unavailable for this architecture — using built-in fallbacks"

# Application code and the versioned curriculum source.
COPY backend/ ./backend/
COPY content/ ./content/

# The built SPA, served by FastAPI on the same port as the API.
COPY --from=frontend /build/dist ./frontend/dist

COPY docker/entrypoint-app.sh docker/entrypoint-backup.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/entrypoint-app.sh /usr/local/bin/entrypoint-backup.sh

# The volume mount point. Declared so a `docker run` without -v still starts,
# though Compose always supplies the named volume.
RUN mkdir -p /data
VOLUME ["/data"]

WORKDIR /app/backend

EXPOSE 3002

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/usr/local/bin/entrypoint-app.sh"]
