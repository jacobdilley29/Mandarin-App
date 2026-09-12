# 台灣華語老師 — Personal Taiwanese Mandarin Teacher

A local, self-hosted web app for learning **Taiwanese Mandarin**: HelloChinese-style
lessons, spaced-repetition review, listening/dictation, pronunciation + tone feedback,
and AI conversation practice. Traditional characters throughout, Taiwan-variant vocab
and pronunciation, oriented toward real day-to-day life in Taiwan.

> **All six tabs are live** — **Learn**, **Review** (FSRS + placement), **Listen**
> (dictation / comprehension / tones), **Speak** (pitch-contour tone feedback),
> **Talk** (Claude roleplay with teacher notes + recap→SRS), and **Me** (a
> mastery-based progress dashboard + settings). Talk needs `ANTHROPIC_API_KEY`;
> without it that one tab is disabled and everything else works.
>
> **Your progress is backed up automatically.** See
> [Backups & restore](#backups--restore) — read it once now, not after you need it.

---

## Quick start

Requires **Docker** with Compose v2.24+ (`docker compose version`).

```bash
git clone <this repo> && cd Mandarin-App
make up                     # builds and starts the app + nightly backup job
```

Open **http://localhost:3002**. That's it — no `.env` needed to start (one is
created from `.env.example` automatically; add your Anthropic key to it later if
you want the Talk tab).

To reach it from your phone: `make tailscale-up`.

Running without Docker is also supported — see [Native Python](#running-without-docker).

---

## Architecture

One Python process serves both the JSON API and the built frontend on a single port.
**Two SQLite databases**, kept deliberately apart (see
[Why two databases](#why-two-databases)).

```
Mandarin-App/
├── docker-compose.yml       app + backup cron, sharing a named volume
├── Dockerfile               one image, two roles (server / backup)
├── docker/                  container entrypoints
├── backend/                 FastAPI + SQLite
│   ├── app/
│   │   ├── main.py          app, routers, static SPA serving
│   │   ├── config.py        settings from .env (with safe defaults)
│   │   ├── db.py            two-database connection (content + ATTACHed progress)
│   │   ├── schema_content.sql   curriculum & dictionary  — regenerable
│   │   ├── schema_progress.sql  SRS, history, settings   — irreplaceable
│   │   ├── migrate.py       one-time split of a pre-existing single-file DB
│   │   ├── backup.py        snapshots, JSON export/import, retention
│   │   ├── taiwanize.py     OpenCC s2twp + pypinyin + Taiwan override layer
│   │   ├── curriculum_source.py  per-unit content files (spec §3.1)
│   │   ├── completeness.py  per-unit checks + the live/draft gate
│   │   ├── levels.py        HSK ↔ TOCFL ↔ CEFR mapping (TOCFL is what's shown)
│   │   ├── placement.py     adaptive band-walking placement check
│   │   ├── content.py       curriculum load + queries + unlock logic
│   │   ├── exercises.py     lesson exercise-stream builder (all drill types)
│   │   ├── validation.py    sentence↔vocab validator (spec §5)
│   │   ├── audio.py         edge-tts synthesis + disk cache
│   │   ├── srs.py           FSRS scheduling wrapper (py-fsrs)
│   │   ├── review.py        review-queue builder + placement check
│   │   ├── listen.py        dictation / comprehension / tone item builders
│   │   ├── textdiff.py      pinyin & character dictation diffing
│   │   ├── tones.py         tone extraction from pinyin
│   │   ├── pitch.py         f0 extraction (numpy autocorrelation)
│   │   ├── tone_classify.py tone classification + sandhi
│   │   ├── speak.py         pronunciation scoring pipeline
│   │   ├── whisper_asr.py   optional faster-whisper wrapper
│   │   ├── conversation.py  Claude roleplay (teacher notes + new words)
│   │   ├── progress.py      activity logging + dashboard stats
│   │   └── routers/         health · admin · content · settings · learn ·
│   │                        review · listen · speak · talk · progress · audio
│   ├── scripts/             backup · export_progress · import_progress ·
│   │                        migrate_split_db · restore_progress ·
│   │                        coverage · load_content · split_curriculum ·
│   │                        build_skeleton · generate_content · warm_audio ·
│   │                        import_cedict
│   ├── tests/               pytest
│   └── requirements.txt
├── frontend/                React + TypeScript + Vite + Tailwind
│   ├── src/pages/           Learn / Review / Listen / Speak / Talk / Me
│   ├── src/components/      TabBar, ToneMark, Speakable, PlayButton, …
│   └── src/theme.ts         design tokens (mirror of DESIGN.md)
├── content/                 versioned curriculum source (spec §3.1)
│   ├── curriculum.json      manifest: metadata + unit order
│   ├── units/               one JSON file per unit — the curriculum itself
│   ├── taiwan_overrides.json  PRC→Taiwan words and pinned readings
│   └── wordlists/           vendored HSK 1-4 lists
├── scripts/tailscale-serve.sh   HTTPS phone access over your tailnet
├── DESIGN.md                palette + typography + tone-motif design tokens
├── Makefile                 setup / run / backup / restore / tailscale
└── .env.example             copy to .env
```

**Tech:** Python 3.11+, FastAPI, uvicorn, SQLite · React 18, TypeScript, Vite 6,
Tailwind 3, vite-plugin-pwa · Docker Compose.

### Why two databases

Learner progress is the only thing here that can't be rebuilt. Curriculum content is
generated from the JSON files in `content/`, which are versioned in git; the audio
cache re-synthesises on demand. So they live in separate files:

| File | Holds | If you lose it |
|---|---|---|
| `content.db` | dictionary, vocab, grammar, units, lessons | Reseeds itself on next start |
| `progress.db` | SRS state, lesson completion, tone-attempt history, Talk history, settings | **Gone forever unless you have a backup** |

Both are opened on one connection — `content.db` as `main`, `progress.db` ATTACHed as
`progress` — so queries spanning the two (e.g. `srs_cards JOIN vocab`) work normally.
The one thing given up is cross-file foreign keys, which SQLite can't enforce between
attached databases. That's the point: **a progress row must outlive the content row it
points at**, so regenerating the curriculum can never cascade-delete your review
history.

Only `progress.db` is backed up. That is a deliberate choice, not an oversight.

---

## Backups & restore

> This app existed once before and was lost, because there was no backup. Everything
> below is set up by default — but **do the five-minute restore drill at the bottom
> once**, so you know it works before you need it.

### What runs automatically

`make up` starts two containers: the app, and a `backup` container running cron.

- **Nightly at 03:30** (configurable via `BACKUP_TIME`) it writes two files:
  - `progress-YYYYMMDD-HHMMSS.db` — a binary snapshot, taken with SQLite's online
    backup API. Not a file copy: copying a live SQLite database can capture a torn
    page or miss committed data sitting in the WAL.
  - `export-YYYYMMDD-HHMMSS.json.gz` — a plain-text dump of every progress table.
    Survives SQLite version changes, can be inspected and hand-edited, and is the
    thing to carry to a new machine.
- **One backup runs immediately at container start**, so a fresh deploy is never
  sitting there with nothing.
- **Rolling 30-day window** (`BACKUP_RETENTION_DAYS`). Older files are pruned; the
  most recent snapshot and export are *always* kept regardless of age.

Backups land in `/data/backups` on the `mandarin-data` volume, alongside the
databases — so they survive image rebuilds too.

Check on it any time — the **Me** tab shows the last backup time and turns red if
the job has stopped running, or:

```bash
make backup-status      # when did it last run, how many are kept
make backups-list       # every backup file and its size
make backup             # take one right now
```

### What is and isn't backed up

| | Backed up | Why |
|---|---|---|
| `progress.db` | ✅ | Irreplaceable |
| `content.db` | ❌ | Regenerates from `content/*.json`, which is in git |
| `data/audio/` | ❌ | An edge-tts cache; re-synthesises on demand |

Backing up the other two would multiply the size of every snapshot to protect data
that git already holds.

### Getting a copy off this machine

Rolling local backups protect against app bugs, bad updates and mistakes. They do
**not** protect against losing the machine. Take a copy off it periodically:

```bash
make export FILE=~/Dropbox/mandarin-progress.json
```

One file, human-readable, everything that matters. Put it wherever you keep things
you'd hate to lose. (Automated off-host sync is deliberately not wired up — see
spec §9; this one command is the baseline.)

### Restore — from a JSON export

The usual path. Works between machines and across app versions:

```bash
make restore FILE=mandarin-progress.json   # replaces all progress
make import  FILE=mandarin-progress.json   # merges into what's there
```

Both take a safety snapshot of the current state first, so a mistaken restore is
itself recoverable. `restore` gives you five seconds to Ctrl-C.

You can also do it from the app: `POST /api/admin/import` with
`{"mode": "replace", "data": {…}}`, or upload the file to
`POST /api/admin/import-file?mode=replace`.

### Restore — from a binary snapshot

Byte-exact, and the fastest way back if the database file itself got corrupted:

```bash
docker compose stop app                              # stop writers first
docker compose run --rm -T app sh -c \
  'cp /data/backups/progress-20260912-033000.db /data/progress.db && rm -f /data/progress.db-wal /data/progress.db-shm'
docker compose start app
```

Removing the `-wal` / `-shm` sidecars matters: they belong to the *old* database and
would otherwise be replayed on top of the restored one.

### Full disaster recovery — new machine, nothing but a backup file

```bash
git clone <this repo> && cd Mandarin-App
make up                                       # fresh install, empty progress
make restore FILE=/path/to/mandarin-progress.json
```

Your lessons, SRS schedule, streak and history come back. The curriculum rebuilds
itself from git. **The only thing you need off the old machine is one export file** —
which is exactly why `make export` is worth running now and then.

### Verifying backups actually work — do this once

Five minutes, and then you know:

```bash
make export FILE=/tmp/before.json          # 1. snapshot your real state
make backup-status                         # 2. confirm the job is running

# 3. break it on purpose:
docker compose stop app
docker compose run --rm -T app sh -c 'rm -f /data/progress.db*'
docker compose start app
#    open the app — progress is gone, as expected

make restore FILE=/tmp/before.json         # 4. bring it back
#    open the app — streak, SRS queue and completed lessons are back
```

If step 4 doesn't restore you exactly, find out now rather than later.

### Things that will and won't destroy your data

| Command | Your progress |
|---|---|
| `make down`, `docker compose down` | ✅ Safe — kept on the named volume |
| `make rebuild`, `docker compose build --no-cache` | ✅ Safe — the image is stateless |
| `make clean` | ✅ Safe — only build artefacts |
| `docker compose exec app python -m scripts.load_content` | ✅ Safe — only touches `content.db` |
| **`docker compose down -v`** | ❌ **Deletes everything, backups included** |
| **`docker volume rm mandarin-data`** | ❌ **Same** |

Only the last two are dangerous, and both need the explicit flag. Keep an off-machine
export and even those are survivable.

### Upgrading from the single-database layout

Earlier versions kept everything in one `data/mandarin.db`. On first start the app
splits it automatically into `content.db` + `progress.db` and renames the original to
`mandarin.db.pre-split.bak` — it is never deleted. Run it by hand first if you'd
rather watch it happen:

```bash
cd backend && python -m scripts.migrate_split_db
```

If you only want the *progress* out of an old backup — because the live database
already has progress you want to keep — use `scripts/restore_progress.py` instead,
which merges rather than converts and drops rows whose content no longer exists:

```bash
cd backend && python -m scripts.restore_progress --from ../data/mandarin.db.pre-split.bak --dry-run
```

---

## Access from your phone (Tailscale Serve)

Microphone capture (the Speak tab) requires HTTPS. Tailscale Serve gives your machine
a trusted HTTPS URL reachable from your phone on your tailnet — no port-forwarding,
no certificates, nothing exposed to the public internet.

1. Install [Tailscale](https://tailscale.com/) on this machine and your phone, signed
   into the same tailnet.
2. Start the app: `make up`.
3. `make tailscale-up` — it prints your `https://<machine>.<tailnet>.ts.net/` URL.
4. Open that on your phone and **Add to Home Screen** to install the PWA.

`make tailscale-down` stops serving; `make tailscale-status` shows what's currently
served.

> The app binds to **loopback only** (`127.0.0.1:3002`) — Tailscale is the sole
> remote path in, and the security perimeter. There's no login, by design. Keep your
> tailnet private.

---

## Configuration (`.env`)

| Key | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(empty)* | Enables the **Talk** conversation tab. Absent → tab disabled, everything else works. |
| `WHISPER_MODEL` | `small` | Local speech model for pronunciation scoring. |
| `PORT` | `3002` | Host port. The container always listens on 3002 internally. |
| `HOST` | `0.0.0.0` | Bind address inside the container. |
| `DATA_DIR` | `./data` | Where databases, audio cache and backups live. Compose sets this to `/data`. |
| `BACKUP_RETENTION_DAYS` | `30` | Rolling backup window. |
| `BACKUP_TIME` | `03:30` | When the nightly backup runs. |

The Anthropic key can also be set in-app on the **Me** tab, which stores it in
`progress.db` and overrides `.env`.

---

## Running without Docker

Requires **Python 3.11+** and **Node 18+**. Data goes in `./data` instead of the
named volume.

```bash
cp .env.example .env
make setup                  # venv + backend deps + npm install + build frontend
make run                    # http://localhost:3002
```

Every backup target works here too (`make backup`, `make export`, `make restore` — they
detect whether the container is running and act accordingly). The **nightly** job is the
one thing Compose provides that this doesn't, so schedule it yourself:

```cron
30 3 * * * cd /path/to/Mandarin-App/backend && ../.venv/bin/python -m scripts.backup
```

### Development workflow (hot reload)

```bash
make dev-backend            # terminal 1 — FastAPI on $PORT
make dev-frontend           # terminal 2 — Vite on http://localhost:5173
```

Vite proxies `/api` and `/audio` to the backend. Use **http://localhost:5173**.

### Tests

```bash
make test
```

---

## Content pipeline

The curriculum ships **committed and validated**, so the app runs with no
downloads and no API key. Everything below is authoring tooling.

### Where the content lives

```
content/curriculum.json      manifest — metadata, function words, unit order
content/units/<unit>.json    one file per unit: lessons, vocab, grammar,
                             sentences, dialogue, and its status
content/hsk1.json            HSK 1 pool for the placement check
content/listen.json          listening comprehension sets
content/taiwan_overrides.json   editorial layer — PRC→Taiwan words, pinned readings
content/wordlists/hsk{1..4}.json  vendored HSK lists (MIT; glosses CC BY-SA 4.0)
```

One file per unit, per spec §3.1: a curriculum change is a reviewable diff
against one unit, not against a 15,000-line blob.

### Live units and drafts

Every unit is either **live** (taught) or **draft** (staged but withheld). The
status is not a label anyone sets by hand — it is computed from completeness
checks on every load, and a unit declared live that fails a required check is
demoted automatically.

| Required to go live | Optional |
|---|---|
| has lessons · vocabulary seeded · every word glossed with a reading · every word has an example sentence · grammar point per lesson · drill sentences per lesson | dialogue per lesson · a Taiwan usage note |

**Drafts never reach Learn.** They cannot be unlocked, cannot become lesson one,
and cannot gate the lessons after them, whatever their position in the order.

This exists for a reason. An earlier expansion to 1,208 words generated the
vocabulary mechanically and shipped it — word lists with dictionary glosses, no
sentences, ordered ahead of the hand-authored Taiwan units, so they became the
first thing in the app. It had to be reverted. The gate makes that structurally
impossible rather than a thing to remember.

```bash
make coverage                    # what's taught, what's staged, what each draft lacks
make coverage ARGS=--all         # include the complete units
```

Currently: **14 units live** (107 words, hand-authored, Taiwan daily-life themes)
and **63 draft** (1,101 words covering the rest of HSK 1–4).

### How a word becomes a lesson

1. **Source** — vendored HSK 1–4 lists plus CC-CEDICT glosses.
2. **Characters** — OpenCC `s2twp`, not plain `s2t`: it substitutes Taiwan
   vocabulary as well as converting characters (自行車, 軟體, 資訊, 印表機).
3. **Vocabulary** — `content/taiwan_overrides.json` covers what `s2twp` misses,
   verified gaps included: 地鐵→捷運, 公共汽車→公車, 西紅柿→番茄, 服務員→服務生,
   聯繫→聯絡, 一會兒→一下 (Taiwan avoids erhua).
4. **Readings** — pypinyin with tone diacritics, then pinned Taiwan readings:
   垃圾 `lèsè`, 企業 `qìyè`, 星期 `xīngqí`, 和 `hàn`, plus the words Taiwan keeps
   fully toned where the mainland standard neutralises them (喜歡 `xǐhuān`,
   早上 `zǎoshàng`). All of this lives in `app/taiwanize.py`, so every script
   applies identical rules.
5. **Structure** — `build_skeleton.py` bins words into units and lessons, as drafts.
6. **Content** — `generate_content.py` writes the sentences, dialogues and grammar,
   then promotes a unit only if it both validates and is complete.
7. **Audio** — `warm_audio.py` pre-generates zh-TW clips for the live units.

Every sentence is checked so it only uses characters the learner has met by that
point; `load_content` refuses to load violations, and generation refuses to
promote a unit that has any.

### The commands

```bash
make check-content       # validate without loading
make load-content        # validate + load into content.db
make build-skeleton      # rebuild the HSK draft units (idempotent, offline)
make warm-audio          # pre-generate audio for live units
make warm-audio ARGS=--dry-run
```

Reading audit — which words have a reading no heuristic can settle:

```bash
cd backend && python -m scripts.build_skeleton --report-readings
```

### Completing the drafts (needs an API key)

The 63 draft units have vocabulary but no sentences. Filling them in is the one
step that needs the Claude API.

Put your key in **any** of these — all three are checked, in this order:

1. the **Me** tab in the app (stored with your progress; no file editing, and it
   enables the Talk tab at the same time)
2. `ANTHROPIC_API_KEY` in `.env` at the repo root
3. `export ANTHROPIC_API_KEY=...` in your shell

Then:

```bash
make generate-content ARGS=--dry-run          # see the plan first
make generate-content ARGS="--unit u_hsk1_01" # one unit, to check the output
make generate-content ARGS="--level 1"        # a whole level
make generate-content                         # everything still in draft
```

**Scale:** 185 lessons across the 63 drafts, one API call each. Results are
cached under `content/.generated/`, so an interrupted run resumes for free and a
re-run costs nothing. Start with one unit and read what it produced before
committing to a level — the model's output becomes Jacob's curriculum.

Each unit is promoted the moment it passes both gates, so progress is
incremental and a failed unit simply stays a draft. Afterwards:

```bash
make coverage && make load-content && make warm-audio
```

### CC-CEDICT

```bash
cd backend && python -m scripts.import_cedict     # downloads the dictionary
```

Needs network; not required to run the app.

**Audio:** `/api/audio` synthesises zh-TW speech with edge-tts and caches mp3s
under `$DATA_DIR/audio/`. If a clip can't be generated (offline, restricted
network), the endpoint returns 503 and the UI degrades gracefully — the audio
button produces no sound rather than breaking the exercise.

## Levels and placement

The app labels levels by **TOCFL**, the exam track that matters here, with the
HSK grade the content is sourced by as a secondary line (spec §3.1):

| Shown | Secondary | CEFR |
|---|---|---|
| Novice 準備級 | HSK 1 | pre-A1 |
| Level 1 入門級 | HSK 2 | A1 |
| Level 2 基礎級 | HSK 3 | A2 |
| Level 3 進階級 | HSK 4 | B1 |

The mapping is data (`content/tocfl_mapping.json`), read only by `app/levels.py`,
so every screen labels a level the same way and a correction is a content diff.

> TOCFL's own vocabulary targets run ahead of HSK 2.0 at every band — Level 3
> expects ~2,500 words against HSK 4's 1,200 cumulative. Finishing HSK 4 here
> covers Level 3's themes and grammar but roughly half its vocabulary, which is
> why the UI says "aligned to" and never "covers".

### The placement check

Adaptive rather than a fixed quiz. It starts mid-range, asks a short round, and
steps up or down until it finds the boundary between what you know and what you
don't — three or four rounds of eight items, spanning HSK 1–4. Each round mixes
the three kinds the spec names: recognition, listening (audio only, no
characters), and sentence building.

**It seeds cards only for the words it actually asked.** A band judged "known"
does not mass-seed hundreds of mature cards — claiming you know 611 HSK 4 words
on the strength of eight questions would fill the review queue with material you
have never seen, and FSRS would take months to work that back out. The band
verdict is stored separately, in `band_state`, as what it is: an estimate of
where to start.

| Endpoint | Purpose |
|---|---|
| `GET /api/placement` | Start — the first band's round |
| `POST /api/placement/round` | Score a band → next round, or the summary |
| `GET /api/placement/summary` | Band verdicts and where to start |
| `POST /api/placement/reset` | Retake it (keeps SRS history) |

## Admin API

| Endpoint | Purpose |
|---|---|
| `GET /api/admin/backup-status` | Last backup time, count, retention |
| `POST /api/admin/backup` | Run a backup now |
| `GET /api/admin/export` | Download all progress as JSON |
| `POST /api/admin/import` | Restore from a JSON body (`mode`: `merge`\|`replace`) |
| `POST /api/admin/import-file` | Same, as a file upload |
| `GET /api/content/coverage` | Per-unit completeness from the source files |
| `GET /api/content/coverage/db` | The same as loaded into the database |

---

## Design

The visual identity is documented in **`DESIGN.md`**: a palette drawn from Taiwan
signage green + temple vermilion, Noto Serif/Sans TC typography with characters as the
hero, and the four-tone contour shapes as a recurring motif. Light and dark modes both
supported.

See `mandarin-teacher-spec.md` for the full specification.

## The `legacy/` prototype

An earlier, self-contained static PWA prototype (vanilla JS, no backend) lives in
`legacy/` for reference. It is not part of the new app and is not served.
