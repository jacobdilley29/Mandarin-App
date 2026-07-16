# 台灣華語老師 — Personal Taiwanese Mandarin Teacher

A local, self-hosted web app for learning **Taiwanese Mandarin**: HelloChinese-style
lessons, spaced-repetition review, listening/dictation, pronunciation + tone feedback,
and AI conversation practice. Traditional characters throughout, Taiwan-variant vocab
and pronunciation, oriented toward real day-to-day life in Taiwan.

> **Status: Phase 3 (Listen).** Learn + Review plus a full **Listen** tab:
> **dictation** (hear a sentence at 0.75×/1×/1.25×, type characters or pinyin,
> get a diff-highlighted correction), **comprehension** dialogues with
> questions (two zh-TW voices, one per speaker), and **tone ear-training**
> (single-tone and tone-pair drills using the four tone-contour shapes).
> Speak / Talk arrive in later phases (honest "coming soon" placeholders).

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
│   │   ├── schema.sql       full domain schema
│   │   ├── content.py       curriculum load + queries + unlock logic
│   │   ├── exercises.py     lesson exercise-stream builder (all drill types)
│   │   ├── validation.py    sentence↔vocab validator (spec §5)
│   │   ├── audio.py         edge-tts synthesis + disk cache
│   │   ├── srs.py           FSRS scheduling wrapper (py-fsrs)
│   │   ├── review.py        review-queue builder + placement check
│   │   ├── listen.py        dictation / comprehension / tone item builders
│   │   ├── textdiff.py      pinyin & character dictation diffing
│   │   ├── tones.py         tone extraction from pinyin
│   │   └── routers/         health, settings, learn, review, listen, audio
│   ├── scripts/             import_cedict · load_content · generate_content
│   ├── tests/               pytest (validation, exercise builder)
│   └── requirements.txt
├── frontend/                React + TypeScript + Vite + Tailwind
│   ├── src/
│   │   ├── pages/           Learn (+ learn/) / Review (+ review/) / … / Me
│   │   ├── components/      TabBar, ToneMark, Speakable, PlayButton, …
│   │   ├── audio.ts         tappable-audio playback hook
│   │   └── theme.ts         design tokens (mirror of DESIGN.md)
│   └── package.json
├── content/curriculum.json  seed curriculum (Traditional, Taiwan usage, validated)
├── content/hsk1.json        HSK 1 foundation pool for the placement check
├── content/listen.json      listening comprehension sets (validated)
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

## Content pipeline

The curriculum ships **committed and validated** in `content/curriculum.json`
(Traditional characters, Taiwan usage), so the app runs with no downloads or API
key. Three scripts (run from `backend/`, with the venv active) support authoring:

```bash
python -m scripts.load_content            # validate + load content into SQLite
python -m scripts.load_content --check    # validate only (vocab/sentence check)
python -m scripts.import_cedict           # download + import CC-CEDICT dictionary
python -m scripts.generate_content        # (optional) regenerate/expand via Claude API
```

Every sentence is checked so it only uses characters the learner has met by that
point in the curriculum; `load_content` refuses to load content with violations.
`import_cedict` and `generate_content` need network / an `ANTHROPIC_API_KEY`
respectively and are **not** required to run the app.

**Audio:** the `/api/audio` endpoint synthesises zh-TW speech with edge-tts and
caches mp3s under `data/audio/`. If a clip can't be generated (offline, or a
restricted network), the endpoint returns 503 and the UI degrades gracefully —
the audio button simply produces no sound rather than breaking the exercise.

---

## Roadmap (build phases)

Each phase ends runnable.

- **Phase 0 — skeleton ✅:** FastAPI + Vite scaffold, SQLite schema, settings
  page, PWA manifest, design tokens, six-tab shell.
- **Phase 1 — Content + Learn ✅:** validated Taiwan-Mandarin curriculum,
  curriculum browser, full lesson exercise engine (all non-speaking drills),
  edge-tts audio with disk caching, completion → SRS enrolment, plus the content
  pipeline scripts (CC-CEDICT import, content loader, Claude-based generator).
- **Phase 2 — Review ✅:** FSRS scheduling (py-fsrs), first-run placement
  check over an HSK 1 foundation pool, daily review queue with rotating card
  types and Again/Hard/Good/Easy rating.
- **Phase 3 — Listen ✅ (this):** dictation with pinyin/character diffing,
  comprehension dialogues + questions, and tone ear-training (single + tone-pair).
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
