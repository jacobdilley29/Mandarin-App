-- 台灣華語老師 — PROGRESS schema (attached database: progress.db, schema name "progress")
--
-- Everything in this file is IRREPLACEABLE. It is the record of what Jacob has
-- actually done: SRS scheduling state, lesson completion, pronunciation history,
-- tutor conversations and settings. None of it can be regenerated from source
-- data, so per spec §7 it lives in its own SQLite file that app updates,
-- image rebuilds and curriculum reseeds never touch.
--
-- Single-user app (no auth): user-scoped state lives in singleton rows.
--
-- NOTE ON FOREIGN KEYS: columns pointing at content tables (lesson_id,
-- grammar_id, vocab_id, exercise_id) carry NO REFERENCES clause. SQLite cannot
-- enforce a foreign key across attached databases — and here that is the point,
-- not a limitation: a progress row must survive its content row being wiped and
-- reseeded. Foreign keys *within* this file are kept and enforced.

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- Meta / migrations
--
-- Deliberately NOT called schema_meta: content.db uses that name, and with both
-- files attached to one connection an unqualified name resolves to main first,
-- which would make this table unreachable.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS progress_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- Lesson completion state
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lesson_progress (
    lesson_id     TEXT PRIMARY KEY,            -- content lessons.id (cross-DB, unenforced)
    completed     INTEGER NOT NULL DEFAULT 0,  -- 0/1
    best_score    REAL,                        -- 0..1
    unlocked      INTEGER NOT NULL DEFAULT 0,  -- 0/1
    completed_at  TEXT
);

-- ---------------------------------------------------------------------------
-- Spaced repetition (FSRS)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS srs_cards (
    id            INTEGER PRIMARY KEY,
    item_type     TEXT NOT NULL,          -- 'vocab' | 'grammar'
    item_id       TEXT NOT NULL,          -- content vocab/grammar id (cross-DB, unenforced)
    card_type     TEXT NOT NULL,          -- recognition|recall|audio_meaning|cloze|speak
    -- FSRS state (py-fsrs v5 Card serialization):
    stability     REAL,
    difficulty    REAL,
    due           TEXT,                   -- ISO datetime (UTC)
    last_review   TEXT,                   -- ISO datetime (UTC)
    step          INTEGER,                -- FSRS learning/relearning step index
    reps          INTEGER NOT NULL DEFAULT 0,
    lapses        INTEGER NOT NULL DEFAULT 0,
    state         TEXT NOT NULL DEFAULT 'new', -- new|learning|review|relearning
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_srs_due ON srs_cards(due);
CREATE INDEX IF NOT EXISTS idx_srs_item ON srs_cards(item_type, item_id);

CREATE TABLE IF NOT EXISTS review_log (
    id          INTEGER PRIMARY KEY,
    card_id     INTEGER NOT NULL REFERENCES srs_cards(id) ON DELETE CASCADE,
    rating      INTEGER NOT NULL,         -- 1 Again .. 4 Easy
    reviewed_at TEXT NOT NULL DEFAULT (datetime('now')),
    elapsed_ms  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_reviewlog_card ON review_log(card_id);

-- Drill error log -> feeds "weakest grammar points" on the dashboard.
CREATE TABLE IF NOT EXISTS drill_errors (
    id          INTEGER PRIMARY KEY,
    exercise_id INTEGER,                  -- content exercises.id (cross-DB, unenforced)
    grammar_id  TEXT,                     -- content grammar.id  (cross-DB, unenforced)
    vocab_id    TEXT,                     -- content vocab.id    (cross-DB, unenforced)
    detail      TEXT,
    occurred_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Per-syllable tone attempt log -> tone-accuracy trend on the dashboard.
CREATE TABLE IF NOT EXISTS tone_attempts (
    id          INTEGER PRIMARY KEY,
    target_text TEXT NOT NULL,
    correct     INTEGER NOT NULL,        -- count of syllables matched
    total       INTEGER NOT NULL,
    detail      TEXT,                    -- JSON per-syllable verdicts
    occurred_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- Talk (conversation) — history held server-side per session
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS talk_sessions (
    id          TEXT PRIMARY KEY,        -- uuid
    scenario    TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS talk_messages (
    id          INTEGER PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES talk_sessions(id) ON DELETE CASCADE,
    role        TEXT NOT NULL,           -- user|assistant
    content     TEXT NOT NULL,
    teacher_note TEXT,                   -- corrections + nicer phrasing (assistant turns)
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_talkmsg_session ON talk_messages(session_id);

-- ---------------------------------------------------------------------------
-- User settings & stats (singleton row, id = 1)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS settings (
    id                 INTEGER PRIMARY KEY CHECK (id = 1),
    show_pinyin        INTEGER NOT NULL DEFAULT 1,   -- global default; hidden in review to force recall
    playback_rate      REAL    NOT NULL DEFAULT 1.0, -- 0.75 / 1.0 / 1.25
    tts_voice          TEXT    NOT NULL DEFAULT 'zh-TW-HsiaoChenNeural',
    theme              TEXT    NOT NULL DEFAULT 'system', -- system|light|dark
    daily_new_limit    INTEGER NOT NULL DEFAULT 15,
    reduced_motion     INTEGER NOT NULL DEFAULT 0,
    placement_done     INTEGER NOT NULL DEFAULT 0,
    anthropic_api_key  TEXT,                         -- optional; set in-app to enable Talk (overrides .env). Local single-user store.
    updated_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Daily activity for streak / minutes-per-day.
CREATE TABLE IF NOT EXISTS daily_activity (
    day          TEXT PRIMARY KEY,       -- YYYY-MM-DD
    minutes      REAL NOT NULL DEFAULT 0,
    reviews_done INTEGER NOT NULL DEFAULT 0,
    lessons_done INTEGER NOT NULL DEFAULT 0
);

-- Seed the singleton settings row.
INSERT OR IGNORE INTO settings (id) VALUES (1);
