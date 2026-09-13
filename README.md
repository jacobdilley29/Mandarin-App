# 台灣華語老師 — Personal Taiwanese Mandarin Teacher

A local, self-hosted web app for learning **Taiwanese Mandarin**: HelloChinese-style
lessons, spaced-repetition review, listening/dictation, pronunciation + tone feedback,
and AI conversation and tutoring. Traditional characters throughout, Taiwan-variant
vocab and pronunciation, oriented toward real day-to-day life in Taiwan.

> **All six tabs are live** — **Learn**, **Review** (FSRS + placement + extra
> practice), **Listen** (dictation / comprehension / tones), **Speak**
> (pitch-contour tone feedback), **Talk** (Claude roleplay *and* an
> ask-a-question tutor), and **Me** (a mastery-based progress dashboard +
> settings). Talk needs `ANTHROPIC_API_KEY`; without it that one tab is disabled
> and everything else works.
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
│   │   ├── llm.py           the Claude model id, in one place
│   │   ├── conversation.py  Claude roleplay (teacher notes + new words)
│   │   ├── tutor.py         Claude ask-a-question tutor (curriculum context)
│   │   ├── practice.py      needs-practice + known-material drills (no FSRS writes)
│   │   ├── progress.py      activity logging + dashboard stats
│   │   └── routers/         health · admin · content · settings · learn ·
│   │                        review · practice · listen · speak · talk ·
│   │                        tutor · progress · audio
│   ├── scripts/             backup · export_progress · import_progress ·
│   │                        migrate_split_db · restore_progress ·
│   │                        coverage · load_content · split_curriculum ·
│   │                        build_skeleton · generate_content · warm_audio ·
│   │                        import_cedict
│   ├── tests/               pytest
│   ├── requirements.txt         hard requirements — must install everywhere
│   └── requirements-accel.txt   optional accelerators, installed best-effort
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
| `progress.db` | ✅ | Irreplaceable — SRS, completion, streak, **roleplay and tutor history** |
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

> **If you installed from the Mac App Store**, its CLI lives inside the app
> bundle (`/Applications/Tailscale.app/Contents/MacOS/Tailscale`) and is never
> put on your `PATH` — only the standalone and Homebrew builds do that.
> `make tailscale-up` looks in the bundle too, so either build works; if it still
> says it can't find the command, the app genuinely isn't installed.

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

> **macOS ships Python 3.9 as `python3`**, which is too old — several
> dependencies are 3.11-only. `make setup` looks for `python3.13`, `python3.12`
> and `python3.11` before falling back, and stops with a one-line message if it
> finds none, so you never have to read a pip resolver error to learn this.
> `brew install python@3.12` is enough. Docker needs no Python at all.

```bash
cp .env.example .env
make setup                  # venv + backend deps + npm install + build frontend
make run                    # http://localhost:3002
```

If `backend/.venv` already exists from an older interpreter, `make setup` says
so and tells you to `rm -rf backend/.venv` first. Point it at a specific
interpreter with `make setup PY=/opt/homebrew/bin/python3.12`.

Every backup target works here too (`make backup`, `make export`, `make restore` — they
detect whether the container is running and act accordingly). The **nightly** job is the
one thing Compose provides that this doesn't, so schedule it yourself:

```cron
30 3 * * * cd /path/to/Mandarin-App/backend && .venv/bin/python -m scripts.backup
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

**What "out of scope" means.** A sentence may only use characters the learner has
met: the vocabulary of every lesson up to that point, the function-word
allowlist, and the **HSK 1 placement pool** (`content/hsk1.json`) — 42 words
seeded into the deck as already-mastered by the placement check and never taught
in a lesson. That last part is easy to forget: the generator once omitted it
while the loader included it, so the generator rejected ordinary sentences using
老師, 學校 and 朋友 and threw away 17 of 23 units in a run. Both now read the same
`validation.placement_pool_chars()`.

When a lesson does break scope, it is re-asked **once**, told exactly which
characters were rejected, and the better version replaces the cached one. Pass
`--no-retry` to skip that — it saves a call and loses the lesson.

A blocked unit is still a draft, so a later `make generate-content` picks it up
again and retries it. Selection filters on **status, not completeness**: a unit
stopped by one bad sentence has all of its content, so filtering on completeness
skipped exactly the units that needed the retry and reported "every unit in scope
is already complete" about content the learner cannot see.

`make load-content` refuses a violation in a **live** unit and only reports one in
a draft. Drafts are gated out of Learn anyway, and one unfinished draft sentence
should not stop every finished unit from loading.

### Is the sequence continuous?

Completeness and sequencing are different questions. A unit can have every
example, grammar point and sentence it needs — complete — and still lean on a
word that only a **draft** unit teaches, which the learner never sees. That
happened: six generated units were promoted above thirteen still-empty drafts
holding 232 words, and nothing reported it, because the generator validates one
unit against the whole curriculum rather than against the sequence actually
walked.

`make coverage` now answers it directly:

```
✓ sequence is continuous — every live lesson reads from what came before
```

or, when it isn't:

```
○ 9 untaught character(s) across 5 live lesson(s):
      餐  [l_dir_1 sentence 4]  taught in u_food, still a draft
  Fill these drafts to close it: u_food
```

Three ways to be a hole, each named: the word waits in a **draft**, it is taught
in a unit that **comes later**, or it is **taught nowhere at all**. The placement
pool never counts as a hole. `app/sequence.py` runs the existing validator over
live units only — the whole check is that framing. It reports and never blocks;
a hole means a draft below is still empty, which is work to finish rather than an
error in what is already there.

Each unit is promoted the moment it passes both gates, so progress is
incremental and a failed unit simply stays a draft. A unit where *nothing*
generated — an outage, a rate limit — is left untouched on disk rather than
rewritten, so a bad run can never demote finished content to draft.

**Generated content lands in your working tree, not in the container.** Under
Docker the round trip is: the authoring targets rebuild the image first (so the
container runs the code and content currently in your tree), the run happens
inside the container, and the results are copied back out with
`docker compose cp`. After a run, `git status` shows which units changed,
`git diff` shows what the model wrote, and nothing is kept unless you commit it.
`make pull-content` repeats just the copy-back, and is safe to run any time.

Two things this replaced, both worth knowing:

- Output used to be written **inside the container**, where the next image
  rebuild destroyed it — a successful generation run could vanish entirely.
- Bind-mounting `content/` was the obvious fix and **did not work**: Docker
  Desktop on macOS could not read through the mount at all, failing with
  `OSError: [Errno 35] Resource deadlock avoided` and taking
  `/api/content/coverage` down with it. Copying is slower and completely
  reliable. Don't re-add the mount.

The image rebuild also means a `git pull` followed by `make generate-content`
can't execute the previous image's code — a few cached seconds, one less class
of confusion.

Afterwards:

```bash
make coverage && make load-content && make warm-audio
```

### Going TOCFL-native

The curriculum is currently built from **HSK 1–4 word lists with TOCFL labels
mapped over them** — 1,193 words, against the ~2,500 TOCFL Level 3 alone
expects. That is why the UI says "aligned to" and never "covers".

Closing that gap is a change of *source data*, not of the pipeline. Download the
official vocabulary list for a level (SC-TOP, the body that runs the exam,
publishes them), export it to CSV, then:

```bash
make import-tocfl FILE=novice.csv LEVEL=novice ARGS=--dry-run   # check it parsed
make import-tocfl FILE=novice.csv LEVEL=novice                  # write the list
```

The importer matches columns by header in Chinese or English, handles CSV or
TSV, applies the same Taiwan pass everything else gets (垃圾 becomes lèsè
whatever the file says, a Simplified stray is converted), skips junk rows, and
reports how much of the list is genuinely new against what you already have.
`--dry-run` writes nothing — run it first.

The output lands in `content/wordlists/tocfl_<level>.json` in the same shape as
the HSK lists, so `build-skeleton` can bin it into units and `generate-content`
fills them in exactly as before.

> Word lists are inventories of a language and the official ones are published
> for exactly this purpose. Lesson text is someone's work — this app writes its
> own sentences rather than taking them from another site.

### Themed units, not word-list positions

`make build-skeleton` groups words into units by **situation** — 便利商店, 夜市,
捷運, 看醫生, 租房子 — the same shape as the hand-authored units. That needs an
API key, and it is now the default; without a key the build stops and says so
rather than quietly producing something worse.

`ARGS="--theme offline"` is the no-key fallback. It bins words by frequency and
names the result "HSK 3 詞彙 7" — a word-list position wearing a title. It was
the default for months, which is why the generated half of the curriculum reads
nothing like the curated half.

> **Re-theming regroups words but keeps lesson ids** (`l_hsk2_01_1` means "first
> lesson of the first HSK 2 unit", whatever it currently holds). The generation
> cache records which words each entry was written for, so a re-themed lesson is
> a miss reported as `words changed`, not a silent hit serving content written
> for different vocabulary. Re-theming therefore costs a regeneration — that is
> the honest price, not a bug.

### Why theming is chunked

`build_skeleton.py` asks Claude to group a level's words into situational units.
That call is made in batches of `CHUNK_WORDS`, not once per level, because a
whole level does not fit in one response — measured, not assumed: HSK 1's 106
words planned inside 16000 tokens and HSK 2's 129 ran out of them. The plan
itself is small (HSK 1's was 8KB); what consumes the budget is the adaptive
thinking, and placing every word of a level into coherent themes gets harder
faster than the word count grows. HSK 4 is 590 words, so no single call was ever
going to do it.

Each batch is told the themes already chosen — the curated units first, then
whatever this level has produced so far — so the second half of a level
complements the first rather than inventing 夜市 twice. Each batch caches on its
own under `content/.generated/skeleton-hsk{level}-{n}.json`, so a failure costs
only the batch it happened in, and a retry pays for nothing that already worked.

A whole-level plan from before chunking (`skeleton-hsk{level}.json`) is still
honoured as-is. Re-theming a level that is already planned costs money *and*
regroups its words, which invalidates every lesson generated under it.

### What invalidates the generation cache

Each lesson's generated content is cached under `content/.generated/`, so a
re-run is free for anything that hasn't changed. Two things make it a miss, and
both print the reason so a paid run is never a mystery:

* **The lesson's words changed.** Lesson ids are positional (`l_hsk2_01_1` is
  "the first lesson of the first HSK 2 unit"), so re-theming keeps the ids and
  swaps the words underneath them. A cache keyed on the id alone would hand back
  content written for a different word set, print `• cached`, and look like a
  free success.
* **The content is missing a field the prompt now asks for** (`CONTENT_FIELDS`
  in `scripts/generate_content.py`). This is the half that is easy to forget:
  when lessons gained a reading passage, every cached lesson still had exactly
  the same words, so a regeneration would have reported `• cached` for all 185
  of them and applied content with no passage in it — a paid-looking run that
  changed nothing, with no error anywhere.

So a prompt that grows a field invalidates the cache by itself, at the cost of
one regeneration. That is the safe direction.

### A trap worth knowing about: `examples`

Every structured-output model in this app is checked by
`backend/tests/test_output_schemas.py`, which builds the exact schema the
Anthropic SDK sends and asserts that every `$ref` in it resolves.

That test exists because a field named **`examples`** silently breaks the
request. `examples` is a reserved JSON Schema keyword: pydantic emits a `$ref`
for such a field but drops its `$defs` entry, so the API rejects the call with

```
Invalid schema: Reference to non-existent definition: #/$defs/…Example-Input__1
```

The generator and the tutor both hit this on their first real run — 80 failed
calls and nothing generated. Both now send `example_sentences` and rename it back
when the response is applied, so stored content and the frontend are unchanged.
If you add a model, keep field names off the JSON Schema keyword list; the test
will tell you if you don't.

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

**And it opens the content it names.** Lessons unlock two ways: the chain from
spec §3.1 (finish one to open the next), *or* placement — every live unit at or
below the band you were placed in opens immediately, so you start where you
tested rather than at lesson one. They open **unlocked, not completed**, so the
progress dashboard still only counts work you actually did. `content._unlock_map`
is the single source of truth for both rules, so what the Learn tab shows and
what the API will serve cannot drift apart.

> Placement previously changed nothing at all here: it printed "Starting you at
> Level 3" and left the learner looking at a locked curriculum with only lesson
> one of the first unit open. The verdict is retroactive — an install that
> already took the check gets its units opened on the next load, with no retake.

| Endpoint | Purpose |
|---|---|
| `GET /api/placement` | Start — the first band's round |
| `POST /api/placement/round` | Score a band → next round, or the summary |
| `GET /api/placement/summary` | Band verdicts and where to start |
| `POST /api/placement/reset` | Retake it (keeps SRS history) |

## Listening and speaking

**Pitch analysis uses Praat** (via `praat-parselmouth`), not librosa. Spec §4
names both; librosa is deliberately not used, after measuring all three against
synthesised tone contours with known f0 (`backend/tests/test_pitch.py`):

| Tracker | Median error (tones 2/3/4) | Time | Install |
|---|---|---|---|
| **parselmouth** | **0.018–0.028 semitones** | **1–2 ms** | +136 MB |
| numpy fallback | 0.056–0.085 semitones | 5–6 ms | — |
| librosa pyin | 0.108–0.194 semitones | 73 ms (+25 s first call) | +425 MB |

librosa is built for music retrieval; on clean tonal speech it was the least
accurate and by far the slowest. The numpy autocorrelation tracker stays as a
fallback, so a machine without parselmouth still scores tones — a little less
precisely. On a *level* tone both are exact and neither has an edge; Praat's
advantage is on contours that move, which is where tone discrimination is hard.

**On Apple Silicon, Docker runs the fallback.** `praat-parselmouth` publishes no
Linux **arm64** wheel (x86_64, macOS and Windows only), so in a `linux/arm64`
image there is nothing to install. It lives in `backend/requirements-accel.txt`
and is installed best-effort with `--only-binary`, so the build skips it cleanly
instead of trying to compile Praat from source in a base image with no compiler —
which is precisely how it used to fail.

Which tracker you actually got is reported, not left to guesswork:

```bash
curl -s localhost:3002/api/status | grep pitch_tracker    # "praat" or "numpy"
```

To get Praat on an Apple Silicon Mac, run the app **natively** — the macOS arm64
wheel exists, so `make setup && make run` installs it. Tone scoring works either
way; Praat is finer on moving contours.

**Both halves of the pronunciation score** (spec §3.5) now run:

- **Tone accuracy** — per-syllable pitch contour against the expected tone, with
  sandhi applied first, so 你好 is scored as ní hǎo rather than marked wrong for
  being pronounced correctly.
- **Segmental accuracy** — "did you say the right sounds", from local
  transcription via `faster-whisper`. This was previously commented out of
  requirements, so that half of the score never ran. It reports `null` rather
  than zero when transcription is unavailable: the question wasn't asked.

Whisper's word timestamps also place the syllable boundaries. Without them the
utterance is sliced into equal parts, which assumes every syllable takes the
same time — a misplaced boundary classifies the wrong stretch of pitch. The
response flags which was used (`approximate`).

The model (~480 MB for `small`, set by `WHISPER_MODEL`) downloads on **first
use**, not at build time, so the image stays lean and the app starts offline.

**Listening exercises** carry their own slow / normal / native speed control
(§3.4), separate from the app-wide playback rate. Comprehension dialogues play
as audio only — the transcript appears once you've answered, or when you
deliberately ask for it. With the characters on screen from the start it was a
reading exercise with audio attached.

## Reading

### Zhuyin (注音符號) beside pinyin

Zhuyin is Taiwan's native phonetic system — what children learn, what keyboards
use, what Taiwanese dictionaries print. The **Me** tab has a script toggle:
pinyin, 注音, or both, honoured everywhere a reading is shown.

The conversion is the part worth reading about. `backend/app/zhuyin.py`
transcribes **this app's own pinyin**, never the character. pypinyin can go
straight from 銀行 to zhuyin, but it reads it yínxíng; Taiwan says yínháng.
Measured across the 1,208 curriculum words, deriving from characters disagrees
with the stored reading for **9.2%** of them — and the disagreements are exactly
the readings this app exists to get right (和 hàn, 認識 rènshì, 誰 shéi, 東西
dōngxi). Since a card shows pinyin and zhuyin an inch apart, a disagreement is
not a subtle inconsistency; it is two contradictory answers side by side.
Transcribing the pinyin inherits the Taiwan readings, the sandhi and
`content/taiwan_overrides.json` for free.

Two Taiwan conventions it follows: the neutral tone dot goes **before** the
syllable (˙ㄉㄜ), where pypinyin and most Mainland sources trail it; and a
reading it cannot split confidently comes back **empty rather than wrong** — a
garbled transcription beside a character teaches something false, a missing one
teaches nothing.

`tests/test_zhuyin.py` checks the converter against the `bopomofo` field of
every word in `content/wordlists/*.json`: **1,193 of 1,193**, not a claim.

### Tap-to-define

Tap any Han text in a dialogue, drill sentence or passage and the word, its
reading and its gloss appear in place. Leaving the lesson to look a word up is
how reading practice turns into dictionary practice.

```
POST /api/dictionary/annotate   {"text": "..."}  -> tappable spans
GET  /api/dictionary/{word}                      -> one entry
```

**The curriculum answers first, CC-CEDICT second.** The vocab table holds the
Taiwan reading the lesson taught; CC-CEDICT is broader but Mainland-oriented, so
it disagrees on precisely the words this app is careful about. Looking there
first would show one reading in the lesson and another on tap. CC-CEDICT is also
optional — it is a download that may never have been run (see
[CC-CEDICT](#cc-cedict) above), and everything here works with an empty
`dictionary` table, which is the state a fresh install is in.

Segmentation happens server-side for a whole string at once rather than once per
tap: 我要喝水 is four characters but three words, and 便利商店 is one. It is greedy
longest-match against what the app knows, up to four characters, so word
boundaries agree with what the learner has been taught.

### Passages on their own schedule

Every lesson carries a short passage — 60-120 characters of connected prose
written to exactly that lesson's level and held to the same character scope as
the rest of it. The drills teach words one at a time; the passage is where they
come back as a paragraph, which is a different skill and the one that turns into
reading Chinese.

The **Read** tab lists them, and the reader hides the English behind a tap: with
the translation on screen the eye reads it first and the Chinese becomes
decoration. Tap-to-define works inside a passage, so an unknown word does not end
the reading.

**Each passage is FSRS-scheduled in its own right.** Reading a passage once and
never again is how it becomes a text you half-remember rather than one you can
read, so it is rated Again/Hard/Good/Easy on the same four buttons as a card and
a passage that came out hard resurfaces sooner. This is not a second scheduler —
`app/srs.py` already schedules by `(item_type, item_id)`, and a passage is simply
`item_type='passage'` with the lesson id.

Two rules it keeps:

* **A passage unlocks with its lesson, not before.** The prose is built from what
  that lesson taught; served earlier it is exactly the out-of-scope reading the
  content pipeline exists to prevent.
* **Reading never disturbs the vocabulary deck.** Rating a passage moves that
  passage's card and nothing else — the rule practice sessions already keep, for
  the same reason: an extra reading session must not cost you a pile of
  vocabulary reviews the next morning.

Passage cards are also kept out of the review queue and the practice sets, where
they cannot be rendered as flashcards. That filter is `srs.QUEUE_ITEM_TYPES`, and
it is there because without it the symptom is invisible: the queue does not show
a broken item, it just silently comes back shorter than it says.

```
GET  /api/reading              the library — unlocked, due, locked
GET  /api/reading/due          just what FSRS says to reread today
GET  /api/reading/{lesson_id}  one passage, with the words its lesson taught
POST /api/reading/answer       {lesson_id, rating} -> the passage's new schedule
```

Passages arrive with generation, so a curriculum built before they existed shows
an empty Read tab until `make generate-content` runs again.

## Grammar

Grammar is a first-class module, not a footnote on the vocabulary (spec §3.3).

**Taiwan usage notes.** Grammar points carry a note where Taiwan genuinely
diverges from Mainland Mandarin — 有沒有 + verb for past actions, 有 + verb where
the Mainland says 了, 搭 for transport, 給 in places the Mainland uses 幫/替, and
no erhua in 一邊…一邊. Deliberately **not** one note per point: most patterns are
identical in both standards, and a manufactured difference would devalue the
real ones.

**Prerequisites.** A lesson records the grammar it *builds on* separately from
the grammar it *introduces* (`lesson_requires_grammar` vs `lesson_grammar`), and
shows what it rests on. Enforced the way vocabulary prerequisites already are —
`load_content` refuses content where a lesson reaches forward to a point taught
later. Unlock stays linear, so a gap in the graph can never leave you with
nothing to open.

**In review.** Grammar points enter spaced repetition when introduced (§3.6).
They used to be dropped from the queue, so a pattern was taught once and never
seen again. They get drills suited to a pattern rather than a word, rotating:

| Drill | Asks |
|---|---|
| `pattern_recall` | Given the explanation, which pattern is it? |
| `particle_cloze` | 我買＿一個便當 — which word belongs in the blank? |
| `pattern_build` | Reorder the tiles, with the particle as its own tile |

`particle_cloze` also appears in lessons, alongside the vocabulary cloze: the
same sentence, blanking 了 instead of 便當, asks whether the *pattern* is
understood rather than whether the word is known.

## Tutor and practice

### Ask a question (§3.7)

The **Talk** tab has two modes. *Roleplay* is the Taiwan scenario chat — it stays in
character and never explains itself. *Ask* is the opposite: a tutor whose entire job
is explaining, in English, with Traditional/Taiwan examples.

What separates it from a general chat window is the context. Every question is sent
with what the app already knows about where you are:

- the last lesson you finished and the unit it belongs to
- what you have been getting wrong — drill errors and SRS lapses, with counts
- the words you already know, so examples are built from them
- the **focus** item, when the question came from one

Focus is what makes "why is 了 here?" answerable. Grammar cards and vocabulary
intros in a lesson, and cards in a review session, carry an **Ask about this**
action that opens the tutor with that item attached. The id is looked up against
the curriculum rather than trusted, so the prompt describes the real row.

Answers come back structured — explanation, 2–3 example sentences with pinyin and
gloss, an optional Taiwan-usage note, and related curriculum items — so they render
as cards with tappable audio rather than a wall of text.

Needs an API key, like Roleplay, and it is the same key: add it on the **Me** tab
and both modes light up. Without one the mode explains itself and the rest of the
app is unaffected. See [Completing the drafts](#completing-the-drafts-needs-an-api-key)
for where the key can live.

**Tutor history is progress data** (spec §7). Threads are stored in `progress.db`
alongside roleplay — same tables, `kind='tutor'` — so they survive a content reseed
and an app update, and they are in every backup and JSON export.

### Practice sessions (§3.6, §3.1)

The **Review** tab has the daily FSRS queue and, below it, two practice modes that
are *not* the queue:

| Mode | Pulls from |
|---|---|
| **Needs practice** | Your weak spots: SRS lapses, drill errors, and words whose recorded tone attempts score badly |
| **Known material** | What you've mastered — cards in review with stability ≥ 21 days — sampled at random |

Weak spots are ranked by a score summing all three signals, so a word that is bad in
several ways outranks one that is merely bad in one, and each item says why it's
there (`forgotten 3x`, `2 drill errors, tones 40%`).

**Nothing in a practice session touches your review schedule.** No due date moves, no
lapse is recorded, no stability changes — practice never calls the scheduler at all.
You can drill a word you keep forgetting ten times for free. §3.1 asks that review
stop blocking progress; a practice mode that charged you for using it would be the
same mistake inverted. Time spent still counts toward the streak.

The drills are rendered by the review renderers, so they're the ones you already
know, and a test asserts `srs_cards` is byte-identical before and after a session.

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
