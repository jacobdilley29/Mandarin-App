# 台灣華語老師 — Personal Taiwanese Mandarin Teacher

A local, self-hosted web app for learning **Taiwanese Mandarin**: HelloChinese-style
lessons, spaced-repetition review, listening/dictation, pronunciation + tone feedback,
and AI conversation practice. Traditional characters throughout, Taiwan-variant vocab
and pronunciation, oriented toward real day-to-day life in Taiwan.

> **Status: Phase 0 (skeleton).** FastAPI + Vite/React scaffold, SQLite schema,
> working settings page, PWA manifest, dark mode, and the six-tab shell. The Learn /
> Review / Listen / Speak / Talk features arrive in later phases (see the roadmap
> below); their tabs currently show honest "coming soon" placeholders.

---

## Architecture

One Python process serves both the JSON API and the built frontend on a single port.

```
Mandarin-App/
├── backend/                 FastAPI + SQLite
│   ├── app/
│   │   ├── main.py          app, routers, static SPA serving
│   │   ├── config.py        settings from .env (with safe defaults)
│   │   ├── db.py            SQLite connection + schema bootstrap
│   │   ├── schema.sql       full domain schema (later phases fill it in)
│   │   └── routers/         health, settings
│   └── requirements.txt
├── frontend/                React + TypeScript + Vite + Tailwind
│   ├── src/
│   │   ├── pages/           Learn / Review / Listen / Speak / Talk / Me
│   │   ├── components/      TabBar, ToneMark (signature motif), …
│   │   └── theme.ts         design tokens (mirror of DESIGN.md)
│   └── package.json
├── data/                    SQLite DB + audio cache (gitignored; auto-created)
├── legacy/                  the earlier static-PWA prototype, preserved for reference
├── DESIGN.md                palette + typography + tone-motif design tokens
├── Makefile                 setup / build / run
└── .env.example             copy to .env
```

**Tech:** Python 3.11+, FastAPI, uvicorn, SQLite · React 18, TypeScript, Vite 6,
Tailwind 3, vite-plugin-pwa.

---

## Quick start

Requires **Python 3.11+** and **Node 18+**.

```bash
cp .env.example .env        # optional — defaults work out of the box
make setup                  # venv + backend deps + npm install + build frontend
make run                    # serve API + frontend on http://localhost:3002
```

Open **http://localhost:3002**.

### Configure the port

The port is read from `.env` (`PORT=3002` by default in this project; the spec's
canonical default is `3170`). Change it there, or override per-command:

```bash
make run PORT=3005
```

### Development workflow (hot reload)

Run the backend and the Vite dev server in two terminals. Vite proxies `/api` and
`/audio` to the backend, so you get instant frontend reloads:

```bash
make dev-backend            # terminal 1 — FastAPI on $PORT
make dev-frontend           # terminal 2 — Vite on http://localhost:5173
```

Use **http://localhost:5173** during development.

---

## Access from your phone (Tailscale Serve)

Microphone capture (needed for the Speak tab later) requires HTTPS. Tailscale Serve
gives your machine a trusted HTTPS URL reachable from your phone on your tailnet —
no port-forwarding, no certificates to manage.

1. Install [Tailscale](https://tailscale.com/) on both this machine and your phone,
   signed into the same tailnet.
2. Start the app: `make run` (it binds `0.0.0.0`, so it's reachable on the tailnet).
3. Expose it over HTTPS:

   ```bash
   tailscale serve 3002        # or: make serve-tailscale
   ```

   Tailscale prints an `https://<your-machine>.<tailnet>.ts.net/` URL.
4. Open that URL on your phone and **Add to Home Screen** to install the PWA
   (works offline after first load; installable via the manifest).

> Single-user by design — **Tailscale is the security perimeter**, so there's no
> login. Keep the tailnet private.

---

## Configuration (`.env`)

| Key                 | Default  | Purpose |
|---------------------|----------|---------|
| `ANTHROPIC_API_KEY` | *(empty)* | Enables the **Talk** conversation tab. Absent → tab disabled, everything else works. |
| `WHISPER_MODEL`     | `small`  | Local speech model for pronunciation scoring (Phase 4). |
| `PORT`              | `3002`   | Single port for API + frontend. |
| `HOST`              | `0.0.0.0`| Bind address (keep `0.0.0.0` for Tailscale/phone access). |

All user data lives in `data/` (SQLite + audio cache) — back up that one folder.

---

## Roadmap (build phases)

Each phase ends runnable.

- **Phase 0 — skeleton ✅ (this):** FastAPI + Vite scaffold, SQLite schema, settings
  page, PWA manifest, design tokens, six-tab shell.
- **Phase 1 — Content + Learn:** CC-CEDICT import, HSK 2–3 curriculum, lesson
  exercise engine, edge-tts audio with caching.
- **Phase 2 — Review:** FSRS scheduling, placement quiz, review queue.
- **Phase 3 — Listen:** dictation, comprehension sets, tone ear-training.
- **Phase 4 — Speak:** mic capture, faster-whisper scoring, pitch-contour tone feedback.
- **Phase 5 — Talk + Progress:** Claude conversation mode, teacher notes, recap→SRS,
  progress dashboard.

See `mandarin-teacher-spec.md` for the full specification and `DESIGN.md` for the
visual design system.

## Design

The visual identity is documented in **`DESIGN.md`**: a palette drawn from Taiwan
signage green + temple vermilion (not the generic AI-default cream/terracotta),
Noto Serif/Sans TC typography with characters as the hero, and the four-tone contour
shapes as a recurring motif. Light and dark modes both supported.

## The `legacy/` prototype

An earlier, self-contained static PWA prototype (vanilla JS, no backend) lives in
`legacy/` for reference. It is not part of the new app and is not served; the new
FastAPI + React application above supersedes it.
