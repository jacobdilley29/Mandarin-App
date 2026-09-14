"""Taiwan-variant normalisation: characters, vocabulary and readings (spec §5).

Source material for this app comes from mainland-standard corpora — CC-CEDICT and
the HSK word lists. Both need three passes before they are fit for a Taiwan
Guoyu learner, and this module is the single place all three live so that every
ingestion script applies exactly the same rules:

  1. **Characters** — OpenCC `s2twp`, not plain `s2t`. The `p` is phrase-level
     Taiwan vocabulary substitution, and it does real work beyond character
     conversion: 自行车 → 腳踏車, 软件 → 軟體, 信息 → 資訊, 打印机 → 印表機.
  2. **Vocabulary** — a hand-maintained override table for the substitutions
     s2twp does *not* make. Verified gaps include 地鐵 → 捷運, 公共汽車 → 公車,
     西紅柿 → 番茄 and 服務員 → 服務生. The spec anticipates this: automated
     conversion plus manual overrides, not either alone.
  3. **Readings** — pypinyin with `Style.TONE` for diacritics, then pinned Taiwan
     readings where the standards genuinely diverge: 垃圾 lèsè (not lājī),
     企業 qìyè (not qǐyè), 液體 yìtǐ, 和 hàn, 星期 xīngqí, plus the words Taiwan
     keeps fully toned where the mainland standard neutralises them
     (喜歡 xǐhuān, 朋友 péngyǒu, 早上 zǎoshàng).

The override table is data, not code — content/taiwan_overrides.json — so
correcting a reading is a content change, reviewable in a diff, and refreshing a
vendored word list can never clobber the editorial decisions layered on top.

Tone sandhi is deliberately NOT applied here. Stored pinyin is base tones; sandhi
(third-tone, 不, 一) is a display and pronunciation-scoring concern, handled in
app/tones.py and app/tone_classify.py where the surface form is what matters.
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from .config import REPO_ROOT

OVERRIDES_PATH = REPO_ROOT / "content" / "taiwan_overrides.json"

# Syllables that are genuinely neutral in Taiwan too, so a missing tone mark on
# them is correct rather than a mainland artefact.
TRUE_NEUTRAL = {"le", "de", "ma", "ne", "ba", "zhe", "guo", "men", "zi", "tou"}

_TONED = set("āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ")


# ---------------------------------------------------------------------------
# 1. Characters — OpenCC s2twp
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _converter():
    # Imported lazily: OpenCC builds its dictionaries on construction, and the
    # app serves plenty of requests that never touch conversion.
    import opencc

    return opencc.OpenCC("s2twp")


def to_traditional_tw(text: str) -> str:
    """Simplified (or mixed) text -> Traditional with Taiwan phrase substitutions.

    Already-Traditional Taiwan text passes through unchanged, so this is safe to
    run over content that has been converted before.
    """
    if not text:
        return text
    return _converter().convert(text)


# ---------------------------------------------------------------------------
# 2 & 3. The editorial override layer
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def overrides() -> dict:
    if not OVERRIDES_PATH.is_file():
        return {"vocabulary": {"substitutions": [], "phrases": []},
                "canonical_forms": {"by_simplified": {}},
                "readings": {}}
    return json.loads(OVERRIDES_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def substitutions() -> dict[str, dict]:
    """PRC word -> the Taiwan word that replaces it wholesale."""
    return {s["hsk"]: s for s in overrides()["vocabulary"]["substitutions"]}


@lru_cache(maxsize=1)
def prc_forms() -> dict[str, str]:
    """Every PRC form we know a Taiwan replacement for: PRC -> Taiwan.

    Two sources, because they are caught at two different moments. The
    `substitutions` are HSK *vocabulary* entries, swapped at import so the
    Taiwan word is the one taught. The `phrases` never appear as vocabulary at
    all — 早上好 is not an HSK entry — so nothing was looking for them, and they
    arrive inside generated sentences, dialogue and passages instead.

    Merged here so there is one answer to "is this how Taiwan says it", whoever
    is asking.
    """
    vocab = overrides().get("vocabulary", {})
    out = {s["hsk"]: s["taiwan"] for s in vocab.get("substitutions", [])}
    out.update({p["prc"]: p["taiwan"] for p in vocab.get("phrases", [])})
    return out


@lru_cache(maxsize=1)
def reading_overrides() -> dict[str, str]:
    """Word -> pinned Taiwan reading, merged from every reading table."""
    r = overrides().get("readings", {})
    merged: dict[str, str] = {}
    for key in ("core", "spec_6", "full_tone"):
        merged.update({k: v for k, v in (r.get(key) or {}).items() if k != "note"})
    # `corrections` carries {was, is, why}; only the corrected reading matters here.
    for word, entry in (r.get("corrections") or {}).items():
        if isinstance(entry, dict) and "is" in entry:
            merged[word] = entry["is"]
    return merged


@lru_cache(maxsize=1)
def canonical_forms() -> dict[str, str]:
    """Simplified form -> the Traditional spelling this app should teach.

    The vendored lists carry every spelling in `forms`, and forms[0] is
    frequently wrong for us: sometimes an archaic variant (咊 for 和, 㼝 for 碗),
    and sometimes the SIMPLIFIED form itself (听 for 聽, 几 for 幾, 从 for 從),
    which must never reach a Traditional-only app.
    """
    return {k: v for k, v in overrides()["canonical_forms"]["by_simplified"].items()
            if k != "note"}


def canonical_form(simplified: str, forms: list[str] | None = None) -> str | None:
    """The pinned Traditional spelling for a word, or None to keep forms[0]."""
    pinned = canonical_forms().get(simplified)
    if pinned:
        return pinned
    return (forms or [None])[0]


# ---------------------------------------------------------------------------
# Readings — pypinyin + overrides
# ---------------------------------------------------------------------------
def norm_pinyin(p: str) -> str:
    """Compare readings without being fooled by spacing or Unicode form."""
    return unicodedata.normalize("NFC", (p or "").replace(" ", "").lower())


def pinyin_tw(text: str, *, spaced: bool = False) -> str:
    """Toned pinyin for Traditional text, with Taiwan readings applied.

    A whole-word override wins outright — 垃圾 is lèsè, never lā jī — because
    per-character pinyin cannot know the word it sits in. Otherwise pypinyin
    generates it with tone diacritics.
    """
    if not text:
        return text

    pinned = reading_overrides().get(text)
    if pinned:
        return pinned

    from pypinyin import Style, pinyin as _pinyin

    syllables = [s[0] for s in _pinyin(text, style=Style.TONE)]
    return " ".join(syllables) if spaced else "".join(syllables)


def apply_reading(word: str, current: str | None) -> tuple[str, bool]:
    """Pin a Taiwan reading over `current`. Returns (reading, changed)."""
    pinned = reading_overrides().get(word)
    if pinned and norm_pinyin(pinned) != norm_pinyin(current or ""):
        return pinned, True
    return (current or pinyin_tw(word)), False


# ---------------------------------------------------------------------------
# Whole-entry normalisation
# ---------------------------------------------------------------------------
def normalize_entry(entry: dict) -> tuple[dict, list[str]]:
    """Apply the full Taiwan pass to one word-list entry.

    Returns the normalised entry and a list of human-readable notes describing
    what changed, so a rebuild can report its editorial decisions rather than
    making them silently.
    """
    out = dict(entry)
    notes: list[str] = []

    sub = substitutions().get(out.get("traditional", ""))
    if sub:
        notes.append(f"vocab  {out['traditional']} → {sub['taiwan']}")
        out["prc_form"] = out["traditional"]
        out["traditional"] = sub["taiwan"]
        out["pinyin"] = sub["pinyin"]
        out["taiwan_note"] = sub["note"]
        # Both were derived from the word we just replaced.
        out.pop("bopomofo", None)
        out.pop("readings", None)
        return out, notes

    reading, changed = apply_reading(out.get("traditional", ""), out.get("pinyin"))
    if changed:
        notes.append(f"read   {out['traditional']} {out.get('pinyin')} → {reading}")
        out["pinyin"] = reading
        out.pop("bopomofo", None)  # derived from the old reading
    return out, notes


def unresolved_readings(words: list[dict]) -> list[dict]:
    """Words whose reading no heuristic settles confidently — for human review.

    Two classes: polyphonic entries offering more than one reading, and entries
    where the mainland standard neutralises a syllable Taiwan may keep fully
    toned. Surfacing these is the point: a wrong reading silently feeds wrong
    audio to TTS and a wrong target to tone training.
    """
    flagged = []
    for w in words:
        reasons = []
        if len(w.get("readings") or []) > 1:
            reasons.append("polyphonic")

        syllables = (w.get("pinyin") or "").split()
        if len(syllables) > 1:
            toneless = [
                s for s in syllables[1:]
                if not any(c in _TONED for c in unicodedata.normalize("NFC", s))
            ]
            if toneless and not all(
                re.sub(r"[^a-z]", "", s.lower()) in TRUE_NEUTRAL for s in toneless
            ):
                reasons.append("mainland-neutral-tone")

        if reasons:
            flagged.append({
                "traditional": w.get("traditional"),
                "pinyin": w.get("pinyin"),
                "hsk_level": w.get("hsk_level"),
                "readings": w.get("readings"),
                "why": reasons,
            })
    return flagged
