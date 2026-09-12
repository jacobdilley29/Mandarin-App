-- 台灣華語老師 — CONTENT schema (main database: content.db)
--
-- Everything in this file is REGENERABLE. It is rebuilt from the versioned
-- source data in content/*.json (and, for the dictionary, from a CC-CEDICT
-- download). Losing content.db costs a reseed, nothing more.
--
-- Learner progress deliberately does NOT live here — see schema_progress.sql.
-- That separation is spec §7: a content reseed must never be able to touch
-- the data that can't be regenerated.
--
-- Traditional characters everywhere; pinyin is the phonetic aid.
-- Non-goal hooks kept per spec §10: stroke_order and zhuyin columns exist now
-- but stay NULL until (if ever) those features land.

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- Meta / migrations
--
-- Named schema_meta here and progress_meta in the progress DB. The two files
-- are ATTACHed to one connection, where SQLite resolves an unqualified table
-- name by searching main first and then each attached schema — so a name
-- present in both files would shadow the other copy. Keep them distinct.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- ---------------------------------------------------------------------------
-- Dictionary (CC-CEDICT, seeded at setup)
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
    sort_order  INTEGER NOT NULL DEFAULT 0,
    -- Draft gate (spec §3.1). 'live' units are taught; 'draft' units are staged
    -- but withheld from the Learn map until every required completeness check
    -- passes. Generated content lands as draft and promotes itself only once it
    -- is actually finished — see app/completeness.py for why this exists.
    status       TEXT NOT NULL DEFAULT 'live',
    completeness TEXT                    -- JSON checklist, for the coverage report
);
CREATE INDEX IF NOT EXISTS idx_units_status ON units(status);

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

-- Generated exercise stream for a lesson (cards + drills). The API builds the
-- stream dynamically; this table is reserved for pre-baked streams.
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
