# DESIGN.md — 台灣華語老師 design tokens

The visual identity is drawn from the subject: Taiwan street signage and temple
colour, not the generic cream+terracotta AI default. **Typography is the hero** —
Traditional characters are presented large and beautiful; pinyin sits small and
quiet in a humanist sans.

These tokens are the single source of truth. They are mirrored in
`frontend/src/theme.ts` (as the `tokens` object) and consumed by Tailwind via
CSS custom properties defined in `frontend/src/index.css`. Change them here first,
then keep the code in sync.

---

## Palette

Drawn from: **Taiwan road-sign green** (highway/MRT signage), **temple vermilion**
(廟宇 red as a single, disciplined accent), warm paper neutrals, and ink.

### Light (default)

| Token            | Hex        | Role |
|------------------|------------|------|
| `--bg`           | `#F6F4EC`  | Warm paper background (calm, low-chroma) |
| `--surface`      | `#FFFFFF`  | Cards, sheets |
| `--surface-2`    | `#EDEADE`  | Insets, subtle fills |
| `--border`       | `#DED9C8`  | Hairlines, dividers |
| `--ink`          | `#1E2A24`  | Primary text (near-black, green-cast) |
| `--ink-soft`     | `#5B6B62`  | Secondary text, pinyin |
| `--ink-faint`    | `#8A968D`  | Tertiary / disabled |
| `--primary`      | `#00694E`  | Signage green — primary actions, active tab |
| `--primary-ink`  | `#FFFFFF`  | Text on primary |
| `--primary-soft` | `#D8E7E0`  | Primary tint (selected fills, progress track fill) |
| `--accent`       | `#C8352A`  | Temple vermilion — used **sparingly** (single accent) |
| `--accent-soft`  | `#F3D9D5`  | Accent tint |
| `--good`         | `#2E7D5B`  | Correct feedback |
| `--warn`         | `#B8791B`  | Caution / "likely wrong tone" |
| `--bad`          | `#C8352A`  | Incorrect feedback (shares accent) |

### Dark

| Token            | Hex        |
|------------------|------------|
| `--bg`           | `#12171420` → base `#121714` |
| `--surface`      | `#1A211D`  |
| `--surface-2`    | `#232C27`  |
| `--border`       | `#2E3A33`  |
| `--ink`          | `#ECF1ED`  |
| `--ink-soft`     | `#A5B3AB`  |
| `--ink-faint`    | `#6E7C74`  |
| `--primary`      | `#3FB08A`  |
| `--primary-ink`  | `#0A0F0C`  |
| `--primary-soft` | `#1E3A30`  |
| `--accent`       | `#E86A5E`  |
| `--accent-soft`  | `#3A231F`  |
| `--good`         | `#4FBF8B`  |
| `--warn`         | `#D69A3E`  |
| `--bad`          | `#E86A5E`  |

Dark mode follows `prefers-color-scheme` and can be forced with
`data-theme="dark" | "light"` on `<html>`.

---

## Typography

| Role | Family | Notes |
|------|--------|-------|
| Display characters (vocab hero) | **Noto Serif TC**, 600/700 | the identity; large, generous |
| UI Han characters | **Noto Sans TC**, 400/500 | tabs, buttons, body Han |
| Pinyin | **Inter** (humanist sans), 400/500 | small, set above/below the character |
| Latin UI / numbers | **Inter** | |

Type scale (rem): `xs .75 · sm .875 · base 1 · lg 1.125 · xl 1.375 · 2xl 1.875 · hero 4 · hero-lg 5.5`

---

## Spacing & shape

- Spacing unit: **4px**. Scale: 4 · 8 · 12 · 16 · 20 · 24 · 32 · 40 · 48.
- Radius: `sm 8 · md 12 · lg 18 · pill 999`.
- Shadow (light): `0 1px 2px rgba(30,42,36,.06), 0 8px 24px rgba(30,42,36,.06)`.
- **Tap targets ≥ 44px** (mobile-first, one-handed).

---

## Signature element — the tone-contour motif

The four Mandarin tone shapes are the recurring visual language, reused as
progress indicators, feedback marks, and section markers.

| Tone | Shape | Contour (schematic, x 0→1) |
|------|-------|----------------------------|
| 1 高平 | high flat | `— ` level near top |
| 2 上升 | rising | `╱` low→high |
| 3 低降升 | dip | `╲╱` down then up |
| 4 下降 | falling | `╲` high→low |
| 輕 neutral | short dot | a small reduced mark |

Implemented as `frontend/src/components/ToneMark.tsx` (SVG polylines). Colours:
correct = `--good`, wrong = `--warn`/`--bad`, idle = `--ink-faint`.

---

## Motion

- Feedback animations are **subtle** and **must respect `prefers-reduced-motion`**.
- Default transition: `160ms ease-out` for interactive states; `240ms` for sheet/tab transitions.

---

## Audio-first affordance

Every Chinese string in the UI is intended to be tappable to hear it (edge-tts,
wired in Phase 1). In Phase 0 the affordance styling exists; playback arrives with
the audio pipeline.
