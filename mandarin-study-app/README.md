# 學中文 — Study Companion

A small installable web app for practicing pronunciation & tones, listening comprehension,
and grammar in Traditional Mandarin. Vocabulary uses Traditional characters and Hanyu Pinyin.

Everything runs in the browser — no server, no account, no data leaves your phone
(review progress is stored locally on your device).

## What's inside

- **Review** — spaced-repetition flashcards (vocab + grammar together), so what you
  study today comes back right when you're about to forget it.
- **Listen** — hear a sentence spoken aloud, pick its meaning from four options.
- **Speak (Tone Lab)** — hear a reference word, record yourself, and see your pitch
  contour plotted against the target tone shape.
- **Grammar reference** — a browsable list of core HSK1–2 patterns, always available
  from the Home tab.

## Get it on your phone (recommended: GitHub Pages, free & takes ~5 minutes)

1. Create a free GitHub account at github.com if you don't have one.
2. Create a new repository (e.g. `mandarin-app`) — make it Public.
3. Upload every file in this folder to that repository (drag-and-drop works on
   github.com's "Add file → Upload files" screen — keep the `icons/` folder structure).
4. In the repository, go to **Settings → Pages**. Under "Build and deployment",
   set Source to "Deploy from a branch", branch `main`, folder `/ (root)`. Save.
5. GitHub gives you a URL like `https://yourname.github.io/mandarin-app/`. It can
   take a minute or two to go live.
6. Open that URL on your phone in Safari (iPhone) or Chrome (Android).
   - **iPhone:** tap the Share icon → "Add to Home Screen."
   - **Android:** tap the ⋮ menu → "Install app" (or "Add to Home screen").
7. You now have an app icon that opens full-screen, works offline after the first
   load, and remembers your progress between sessions.

Alternative if you'd rather not use GitHub: drag this whole folder onto
[Netlify Drop](https://app.netlify.com/drop) — it gives you a live HTTPS link
instantly, no account required. GitHub Pages is nicer long-term since it's a
stable link you own.

## Why not just use it inside this chat?

Two of your three priorities — **pronunciation/tone recording** and reliable
**audio** — need microphone and speech access that mobile browsers only grant
reliably to a real, top-level HTTPS page, not to embedded/sandboxed views like
a chat artifact. Hosting it this way (even for free, on GitHub Pages) is what
makes the mic-based Tone Lab actually work on your phone.

## Known limitations (so there are no surprises)

- **Text-to-speech voice**: uses your phone's built-in Chinese voice. Quality and
  accent (Taiwan vs. Mainland) depend on what's installed on your device — check
  your phone's language/voice settings if audio doesn't sound right or doesn't
  play at all. The app will show a banner on Home if it can't find one.
- **Tone Lab is visual feedback, not a grade.** It plots your pitch contour next
  to an idealized tone shape so you can see if your rise/fall is in the right
  direction — it's a training aid, not the kind of scored pronunciation grading
  a dedicated app like HelloChinese offers.
- **Starter content**: 60 HSK1–2 vocabulary words and 12 core grammar points, to
  get you going right away. It's easy to add more — see below.

## Adding your own content

Open `data.js`. Each vocabulary entry looks like:

```js
{ id: "v61", hanzi: "新", pinyin: "xīn", en: "new", ex: { hanzi: "這是新的書。", pinyin: "Zhè shì xīn de shū.", en: "This is a new book." } }
```

Add new entries to the `VOCAB` array (unique `id`s), or new grammar points to
`GRAMMAR`, and re-upload the file (or just this one file, if using GitHub's web
editor) — no other changes needed. If you'd like help building out more content
(more HSK2/HSK3 vocab, more grammar points, or importing a list from a textbook
you're using), just ask and I can generate more entries in this same format.
