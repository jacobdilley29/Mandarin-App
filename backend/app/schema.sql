-- 台灣華語老師 — SQLite schema
-- Phase 0 lays down the full domain skeleton so later phases only fill it in.
-- Single-user app (no auth): user-scoped state lives in singleton rows.
-- Traditional characters everywhere; pinyin is the phonetic aid.
--
-- Non-goal hooks kept per spec §10: stroke_order and zhuyin columns exist now
-- but stay NULL until (if ever) those features land.

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- Meta / migrations
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- Dictionary (CC-CEDICT, seeded at setup in Phase 1)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dictionary (
    id           INTEGER PRIMARY KEY,
    traditional  TEXT NOT NULL,
    simplified   TEXT,
    pinyin       TEXT NOT NULL,          -- CC-CEDICT numbered pinyin
    pinyin_tw    TEXT,                   -- Taiwan-variant reading when it differs
    gloss        TEXT NOT NULL,          -- English definition(s), '/'-joined
    zhuyin       TEXT                    -- hook (§10): bopomofo, filled later
);
CREATE INDEX IF NOT EXISTS idx_dictionary_trad ON dictionary(traditional);

-- ---------------------------------------------------------------------------
-- Vocabulary (learnable items, mapped to HSK levels + Taiwan usage)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vocab (
    id           TEXT PRIMARY KEY,        -- content slug, e.g. 'v_bianli'
    traditional  TEXT NOT NULL,
    pinyin       TEXT NOT NULL,
    gloss        TEXT NOT NULL,
    hsk_level    INTEGER,                -- 1..4
    taiwan_note  TEXT,                   -- e.g. "腳踏車 (not 自行車)", pronunciation notes
    example_hanzi   TEXT,
    example_pinyin  TEXT,
    example_gloss   TEXT,
    stroke_order TEXT,                   -- hook (§10): stroke data, filled later
    zhuyin       TEXT,                   -- hook (§10)
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_vocab_trad ON vocab(traditional);
CREATE INDEX IF NOT EXISTS idx_vocab_hsk ON vocab(hsk_level);

-- ---------------------------------------------------------------------------
-- Grammar points
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS grammar (
    id           TEXT PRIMARY KEY,       -- content slug, e.g. 'g_youmeiyou'
    title        TEXT NOT NULL,          -- e.g. "了 (completed action)"
    pattern      TEXT NOT NULL,          -- the structural pattern
    explanation  TEXT NOT NULL,          -- plain-English
    examples     TEXT NOT NULL,          -- JSON array of {hanzi,pinyin,gloss}
    hsk_level    INTEGER,
    sort_order   INTEGER NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------------------
-- Curriculum: units -> lessons -> exercises
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS units (
    id          TEXT PRIMARY KEY,        -- content slug, e.g. 'u_conv'
    title       TEXT NOT NULL,           -- Taiwan daily-life theme
    subtitle    TEXT,
    hsk_level   INTEGER,
    sort_order  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS lessons (
    id          TEXT PRIMARY KEY,        -- content slug, e.g. 'l_conv_1'
    unit_id     TEXT NOT NULL REFERENCES units(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    dialogue    TEXT,                    -- JSON array of dialogue lines
    sentences   TEXT                     -- JSON array of drill sentences (tokens+pinyin+gloss)
);
CREATE INDEX IF NOT EXISTS idx_lessons_unit ON lessons(unit_id);

-- Which vocab / grammar a lesson introduces (drives the n+1 vocab constraint).
CREATE TABLE IF NOT EXISTS lesson_vocab (
    lesson_id  TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    vocab_id   TEXT NOT NULL REFERENCES vocab(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (lesson_id, vocab_id)
);
CREATE TABLE IF NOT EXISTS lesson_grammar (
    lesson_id  TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    grammar_id TEXT NOT NULL REFERENCES grammar(id) ON DELETE CASCADE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (lesson_id, grammar_id)
);

-- Generated exercise stream for a lesson (cards + drills). Phase 1 builds the
-- stream dynamically in the API; this table is reserved for pre-baked streams.
CREATE TABLE IF NOT EXISTS exercises (
    id          INTEGER PRIMARY KEY,
    lesson_id   TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    kind        TEXT NOT NULL,           -- vocab_intro|grammar|match|audio_meaning|
                                         -- tile_build|cloze|listen_type|translate|
                                         -- dialogue|speak_check
    payload     TEXT NOT NULL,           -- JSON, shape depends on kind
    sort_order  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_exercises_lesson ON exercises(lesson_id);

-- ---------------------------------------------------------------------------
-- Progress / completion state (single user)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS lesson_progress (
    lesson_id     TEXT PRIMARY KEY REFERENCES lessons(id) ON DELETE CASCADE,
    completed     INTEGER NOT NULL DEFAULT 0,  -- 0/1
    best_score    REAL,                        -- 0..1
    unlocked      INTEGER NOT NULL DEFAULT 0,  -- 0/1
    completed_at  TEXT
);

-- ---------------------------------------------------------------------------
-- Spaced repetition (FSRS) — wired up in Phase 2
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS srs_cards (
    id            INTEGER PRIMARY KEY,
    item_type     TEXT NOT NULL,          -- 'vocab' | 'grammar'
    item_id       TEXT NOT NULL,          -- FK into vocab/grammar (by type)
    card_type     TEXT NOT NULL,          -- recognition|recall|audio_meaning|cloze|speak
    -- FSRS state:
    stability     REAL,
    difficulty    REAL,
    due           TEXT,                   -- ISO datetime
    last_review   TEXT,
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
    exercise_id INTEGER REFERENCES exercises(id) ON DELETE SET NULL,
    grammar_id  TEXT REFERENCES grammar(id) ON DELETE SET NULL,
    vocab_id    TEXT REFERENCES vocab(id) ON DELETE SET NULL,
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
-- Talk (conversation) — history held server-side per session (Phase 5)
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
