# 學中文 — Study Companion

A small installable web app for practicing pronunciation & tones, listening comprehension,
and grammar in Traditional Mandarin. Vocabulary uses Traditional characters (Taiwan usage)
and Hanyu Pinyin.

Everything runs in the browser — no server, no account. Review progress and settings
are stored locally on your device.

## What's inside

- **Review** — spaced-repetition flashcards covering the full official HSK1 (150 words)
  and HSK2 (149 unique cards, one entry merges 對's two senses) vocabulary, plus 24 core
  HSK1–2 grammar points, all sharing one SM-2-style queue (similar to Anki).
- **Listen** — a **Words / Sentences** toggle. Words mode quizzes short vocabulary
  example sentences; Sentences mode uses a bank of 24 longer, multi-clause sentences
  combining several grammar points, for tougher listening comprehension.
- **Speak** — also has a **Words / Sentences** toggle.
  - *Words*: hear a reference word, record yourself, and see your pitch contour plotted
    against the target tone shape (flat/rising/dip/falling) — **plus** the app runs your
    recording through the browser's speech recognizer and shows exactly what it heard,
    character by character, highlighting which ones didn't come through so you know
    what to work on.
  - *Sentences*: same speech-recognition feedback, applied to the longer sentence bank.
  - A **Needs practice** panel on Home surfaces the words you've mismatched most often.
- **Settings** — a playback-speed control (Slow / Normal / Native) on Home, used
  everywhere audio plays (Review, Listen, Speak).
- **Grammar reference** — browsable anytime from Home.
- Installable, works offline after first load, remembers your progress on-device.

## Get it on your phone (GitHub Pages, ~5 minutes)

1. Unzip this folder on your computer.
2. Create a free GitHub account if you don't have one, and a new **public** repository.
3. **Add file → Upload files**, and drag in the *contents* of the unzipped folder
   (not the folder itself) — `index.html` should end up at the repo's top level,
   alongside `icons/`.
4. **Settings → Pages** → Source: "Deploy from a branch", branch `main`, folder `/ (root)` → Save.
5. The same Settings → Pages screen will show your live link once it's built
   (`https://yourname.github.io/reponame/`), usually within a minute or two.
6. Open that link on your phone and add it to your home screen:
   - **iPhone (Safari):** Share icon → "Add to Home Screen"
   - **Android (Chrome):** ⋮ menu → "Install app"

Alternative with no account: drag the folder onto [Netlify Drop](https://app.netlify.com/drop)
for an instant HTTPS link.

## Why hosted, not run inside a Claude chat?

Pronunciation feedback needs microphone access, and mobile browsers only grant that
reliably to a real, top-level HTTPS page — not to an embedded/sandboxed view like a
chat artifact. Hosting it (even for free) is what makes the Speak tab actually work
on your phone.

## Known limitations

- **Text-to-speech voice** uses your phone's built-in Chinese voice — quality and accent
  depend on what's installed. The app shows a banner on Home if it can't find one.
- **Speech-recognition feedback** (the "what the app heard" feature) sends audio to your
  browser vendor's speech service over the network — it needs an internet connection
  and isn't available in every browser (Chrome has the broadest support). Where it's
  unavailable, Words mode still gives you the local, offline pitch-contour comparison;
  Sentences mode will show a note instead.
- **The diff feedback is a proxy, not a certified grade.** If the recognizer hears a
  different character than the target, that's a strong hint something (often a tone)
  was off — but it's pattern-matching, not a linguist's ear.
- **Pinyin conventions**: a few words are deliberately kept at their **Taiwan Guoyu**
  full-tone pronunciation rather than the Mainland neutral-tone form you'll see in some
  references — e.g. 學生 is *xuéshēng* here (not *xuésheng*), matching how it's actually
  said in Taiwan.

## Adding your own content

Open `data.js`. `VOCAB` and `GRAMMAR` feed spaced-repetition Review; `SENTENCES` feeds
the "Sentences" mode in Listen/Speak. Formats:

```js
// VOCAB
{ id: "v300", hanzi: "新詞", pinyin: "xīncí", en: "new word", level: "HSK2",
  ex: { hanzi: "這是一個新詞。", pinyin: "Zhè shì yí ge xīncí.", en: "This is a new word." } }

// SENTENCES
{ id: "s25", hanzi: "...", pinyin: "...", en: "..." }
```

Add entries with unique `id`s and re-upload the file — no other changes needed. If you'd
like help expanding into HSK3+ vocabulary, or generating more advanced sentences, just ask.
