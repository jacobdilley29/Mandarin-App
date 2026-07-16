# 台灣華語老師 — Personal Taiwanese Mandarin Teacher (Project Spec)

A local, self-hosted web app that teaches Taiwanese Mandarin through HelloChinese-style lesson modules, spaced-repetition review, listening/dictation drills, pronunciation + tone feedback, and AI conversation practice. Target: HSK 2 → 4 content (with HSK 1 review woven in), Taiwan-variant vocabulary and pronunciation throughout, oriented toward real day-to-day life in Taiwan.

---

## 1. Locked decisions

| Decision | Choice |
|---|---|
| Script | **Traditional characters** everywhere. Pinyin as the phonetic aid (toggleable per-exercise; hidden by default in review to force recall). |
| Level frame | HSK levels used as scaffolding, but vocab/pronunciation follow **Taiwan usage** (see §6). |
| Pronunciation feedback | **Fully local**: faster-whisper for recognition + pitch-contour analysis for tones. No paid speech APIs. |
| TTS | **edge-tts** with zh-TW voices (`zh-TW-HsiaoChenNeural` female, `zh-TW-YunJheNeural` male). Cache generated audio to disk. |
| Platform | Localhost web app, accessed from phone via **Tailscale Serve** (HTTPS required for mic). Mobile-first responsive + PWA manifest. |
| Conversation mode | Anthropic API (key in `.env`, `ANTHROPIC_API_KEY`). App must degrade gracefully if key absent (conversation tab disabled, everything else works). |
| Storage | SQLite, single file, in a `data/` dir. |

## 2. Tech stack

- **Backend**: Python 3.11+, FastAPI + uvicorn.
  - `faster-whisper` (small or medium model, configurable) for speech recognition
  - `librosa` (pyin) or `praat-parselmouth` for pitch extraction → tone scoring
  - `edge-tts` for audio generation (async, cache to `data/audio/`)
  - `fsrs` (py-fsrs) for spaced repetition scheduling
  - `anthropic` SDK for conversation mode + dynamic content generation
- **Frontend**: React + TypeScript + Vite. Tailwind for styling. No heavy UI kit — custom components per the design brief (§8).
- **Serving**: FastAPI serves the built frontend. One process, one port (default 3170). User runs `tailscale serve 3170` for phone access.
- **Audio in browser**: MediaRecorder API for mic capture (webm/opus), sent to backend for scoring. Web Audio API for playback-speed control on listening drills.

## 3. Core modules (app tabs)

### 3.1 Learn — structured lessons
HelloChinese-style path: units → lessons → exercise sequence.
- Each **lesson** = 5–8 new vocab items + 1–2 grammar points + a short dialogue, delivered as a mixed exercise stream:
  1. Vocab intro card (character, pinyin, audio, meaning, example sentence)
  2. Grammar point card (pattern, plain-English explanation, 3 examples)
  3. Drills: character↔meaning matching, audio→meaning, sentence tile-building (arrange word tiles into a sentence), fill-in-the-blank (cloze), listen-and-type, translate (multiple choice at first, free-typing later)
  4. Dialogue playthrough (line-by-line audio with optional pinyin/English reveal)
  5. Quick speak check (record yourself saying 2 sentences → tone/pron feedback)
- Progression gates: finish a lesson with ≥80% to unlock the next; new vocab auto-enters the SRS deck.
- Curriculum: seed **Units for HSK 2 and HSK 3** at build time (see §5), designed around Taiwan daily-life themes: 7-Eleven/convenience stores, night markets, MRT/YouBike, ordering food & drinks (bubble tea customization!), renting, banking/post office, small talk & politeness, weather/typhoons, health/pharmacy, work conversations.

### 3.2 Review — SRS
- FSRS-scheduled daily queue mixing HSK 1 (pre-seeded as "learned" after a placement check, see below) with everything learned in-app.
- Card types rotate per item: recognition (char→meaning), recall (meaning→char, multiple choice of similar characters), audio→meaning, cloze in a sentence, and periodic **speak-it** cards.
- Rating buttons: Again / Hard / Good / Easy.
- **Placement check** on first run: quick 30-item adaptive quiz over HSK 1–2; items answered correctly seed the deck with mature FSRS state, misses enter as new.

### 3.3 Listen — comprehension trainer
- **Dictation**: hear a sentence (0.75×/1×/1.25× speed), type what you heard (pinyin or characters via user's IME), diff-highlighted correction.
- **Comprehension sets**: short generated dialogues (2–6 lines) with 2–3 questions each; difficulty tied to current level; only uses learned + n+1 vocab.
- **Tone ear-training**: hear a syllable/word, identify the tone(s). Include tone-pair drills (the 20 tone-pair combinations) since pairs are where learners struggle.
- All audio via cached edge-tts; alternate the two zh-TW voices.

### 3.4 Speak — pronunciation & tones
- **Word/sentence shadowing**: play reference audio → user records → feedback screen shows:
  - Whisper transcription vs. target (per-syllable match/mismatch)
  - Pitch contour plot of the user's recording overlaid on an idealized contour for the expected tone sequence (normalize by speaker pitch range; render as SVG)
  - Per-syllable tone verdict (✓ / likely-wrong-tone with the detected tone)
- Tone scoring approach: segment the recording per syllable using Whisper word timestamps → extract f0 with pyin → normalize → classify against tone templates (1 high-flat, 2 rising, 3 low/dipping, 4 falling, neutral short/reduced) with tone-sandhi rules applied to the *expected* sequence (3-3→2-3, 不/一 sandhi).
- Be honest in the UI that this is approximate ("tone check", not "score to 2 decimals").

### 3.5 Talk — AI conversation practice (Claude API)
- Scenario roleplays set in Taiwan (night market vendor, MRT lost-and-found, landlord, coworker, new friend). Claude plays the character **in traditional characters**, at the user's level, Taiwan register (uses 嗎/喔/耶 particles naturally, Taiwan vocab).
- Two input modes: type, or **speak** (mic → Whisper → text, shown for confirmation before sending).
- Every assistant turn includes a collapsible "teacher note": corrections of the user's last message + one nicer/more natural alternative phrasing.
- Each reply can be played as audio (edge-tts).
- Post-conversation recap: new words encountered → one-tap add to SRS deck.
- System prompt for the roleplay must pin: traditional script, Taiwan usage, level-appropriate vocab (pass the user's known-word list summary), stay in character but gently recast errors.

### 3.6 Progress
- Dashboard: streak, minutes/day, words known by HSK level (stacked bar), tone-accuracy trend, SRS retention, weakest grammar points (from drill error logs).
- Mastery-based framing (no XP inflation): each vocab/grammar item has a mastery state derived from FSRS stability.

## 4. Backend API sketch

```
GET  /api/curriculum                 units + lessons + completion state
GET  /api/lesson/{id}                exercise stream for a lesson
POST /api/lesson/{id}/result         record answers, unlock logic
GET  /api/review/queue               today's FSRS queue
POST /api/review/answer              {card_id, rating} → next due
GET  /api/listen/dictation|set|tones generated exercise payloads
POST /api/speak/score                multipart audio + target text → transcription, per-syllable tones, contour points
GET  /api/audio?text=...&voice=...   cached TTS (returns mp3)
POST /api/talk/message               conversation turn (server holds history per session)
GET  /api/progress                   dashboard stats
```

## 5. Content pipeline (build-time seeding)

- **Dictionary**: CC-CEDICT (has traditional forms + pinyin). Download & parse into SQLite at setup.
- **Word lists**: HSK 1–4 lists → map to traditional forms via CC-CEDICT → apply Taiwan-variant substitutions/annotations (§6).
- **Sentences/dialogues/grammar explanations**: generate at setup time with the Claude API via a `scripts/generate_content.py` script (batched, resumable, output committed as JSON so regeneration is optional). Every generated sentence must be constrained to the vocab available at that point in the curriculum (+ the lesson's new words). Grammar points follow the standard HSK 2–3 sequence (了 usage, 過, 在/正在, comparisons with 比, 把 later, resultative complements, 的/得/地, measure words, etc.), each with pattern + explanation + examples.
- Validate generated content: script checks that sentences only use allowed characters and flags violations for regeneration.

## 6. Taiwan-specific requirements (do not skip)

- Pronunciations: 垃圾 lèsè, 和 hàn (acceptable variant), 星期 xīngqí, 法國 fàguó, 液 yì — annotate where Taiwan differs from PRC standard; TTS zh-TW voices handle most of this natively.
- Vocab preferences: 腳踏車 (not 自行車), 捷運, 便當, 悠遊卡, 週末, 馬鈴薯, 番茄, 沒關係/不會 (as "you're welcome"), 早安/午安, sentence-final 喔/耶/啦 usage notes.
- Culture notes sprinkled into lessons: counting with hands, receipt lottery (統一發票), convenience-store culture, 不好意思 as the universal lubricant.
- Erhua (兒化) de-emphasized; note it as a mainland feature.

## 7. Build phases (implement in order; each phase ends runnable)

1. **Phase 0 — skeleton**: FastAPI + Vite scaffold, SQLite schema, settings page, PWA manifest, serve on 0.0.0.0:3170, README with Tailscale Serve instructions.
2. **Phase 1 — content + Learn**: content pipeline, curriculum browser, full lesson exercise engine (all drill types except speaking), audio via edge-tts with caching.
3. **Phase 2 — Review**: FSRS integration, placement quiz, review queue UI.
4. **Phase 3 — Listen**: dictation, comprehension sets, tone ear-training.
5. **Phase 4 — Speak**: mic capture, Whisper scoring endpoint, pitch-contour visualization, speak drills wired into lessons/review.
6. **Phase 5 — Talk + Progress**: Claude conversation mode, teacher notes, recap→SRS flow, progress dashboard. Polish pass.

Testing expectations: unit tests for FSRS scheduling, sentence-vocab validation, tone classification (fixture audio files), and pinyin/character diffing.

## 8. Design brief (UX/UI)

- **Mobile-first** (primary use is a phone over Tailscale); everything reachable one-handed; big tap targets for drills; bottom tab bar: 學 Learn / 複習 Review / 聽 Listen / 說 Speak / 聊 Talk / 我 Me.
- Clean, calm, focused — one exercise per screen, generous whitespace, immediate feedback animation (subtle, respects reduced-motion).
- Typography is the identity: characters are the hero. Use a quality Traditional-Chinese webfont (e.g., Noto Serif TC for display characters, Noto Sans TC for UI) with a large, beautiful character presentation on vocab cards; pinyin set small above/below in a humanist sans. Avoid the generic cream+terracotta AI-default palette; pick a palette drawn from the subject (e.g., Taiwan street signage green, temple vermilion as a single accent, warm neutral background) — designer's choice, but deliberate and documented in a `DESIGN.md` token file.
- Signature element idea: the tone-contour visual language — the four tone shapes used as a recurring motif (progress indicators, correct/incorrect feedback, section markers).
- Audio-first affordances: every Chinese string in the UI is tappable to hear it.
- Dark mode supported.

## 9. Config & ops

- `.env`: `ANTHROPIC_API_KEY` (optional), `WHISPER_MODEL=small`, `PORT=3170`.
- First-run setup command: `make setup` → venv, deps, download CC-CEDICT + Whisper model, run content generation (skippable, uses committed JSON if present), build frontend.
- All user data in `data/` (SQLite + audio cache) — easy to back up.
- Single-user; no auth (Tailscale is the perimeter).

## 10. Non-goals (v1)

Handwriting/stroke-order practice, zhuyin input training, TOCFL mock exams, multi-user, offline mobile app. Keep hooks in the schema for stroke-order and zhuyin later.
