"""Tone classification from an f0 contour (spec §3.4).

Given a per-syllable pitch contour, decide which Mandarin tone it most resembles
(1 high-flat, 2 rising, 3 low-dipping, 4 falling, 5 neutral). Contours are
normalised into semitones relative to the speaker's own pitch range so the
verdict is speaker-independent. Honestly approximate — a "tone check", not a
graded score.

Tone-sandhi is applied to the *expected* sequence before comparison:
  - 3-3 → 2-3 (a third tone before another third becomes rising)
  - 不 (bù) → bú (2) before a 4th tone
  - 一 (yī) → yí (2) before a 4th tone, yì (4) before 1/2/3
"""

from __future__ import annotations

import numpy as np


def to_semitones(f0: np.ndarray) -> np.ndarray:
    """Voiced f0 → semitones relative to the segment's own median."""
    voiced = f0[~np.isnan(f0)]
    if voiced.size == 0:
        return np.array([])
    ref = float(np.median(voiced))
    return 12.0 * np.log2(voiced / ref)


# Total pitch movement (semitones) below which a syllable reads as a level tone.
_FLAT_RANGE = 2.0


def classify_contour(f0: np.ndarray) -> tuple[int, float]:
    """Classify a single-syllable contour into a tone (1–4) with a confidence.

    A flatness gate catches the (high) level tone 1; otherwise the syllable is
    scored against rising (2), low-dipping (3), and falling (4) templates using
    its linear slope and quadratic curvature. Returns (tone, confidence 0..1);
    empty/too-short → (5, 0) neutral.
    """
    st = to_semitones(f0)
    if st.size < 3:
        return 5, 0.0

    n = st.size
    x = np.linspace(0.0, 1.0, n)
    curv = float(np.polyfit(x, st, 2)[0])  # >0 = U-shaped (dip)
    slope = float(np.polyfit(x, st, 1)[0])
    start = float(np.mean(st[: max(1, n // 5)]))
    lowest = float(np.min(st))
    dip = start - lowest  # how far it dips below where it started
    rng = float(st.max() - st.min())

    # Level tone: little overall movement.
    if rng < _FLAT_RANGE:
        return 1, float(max(0.0, min(1.0, 1.0 - rng / _FLAT_RANGE)))

    scores = {
        2: slope - max(0.0, curv) * 1.2 - max(0.0, dip - 1.5),  # rising, near-linear
        3: max(0.0, curv) * 1.3 + dip * 0.5 - abs(slope) * 0.1,  # dips low then recovers
        4: -slope - abs(curv),                                   # falling, near-linear
    }
    tone = max(scores, key=scores.get)
    ordered = sorted(scores.values(), reverse=True)
    conf = float(1.0 - np.exp(-(ordered[0] - ordered[1])))
    return tone, max(0.0, min(1.0, conf))


# ---------------------------------------------------------------------------
# Tone sandhi on the expected sequence
# ---------------------------------------------------------------------------
def apply_sandhi(hanzi: str, tones: list[int]) -> list[int]:
    """Adjust the *expected* tone sequence for common sandhi.

    `hanzi` is the target characters (used to spot 不/一); `tones` are the base
    citation tones. Length of `hanzi` (Han chars) should match `tones`.
    """
    han = [c for c in hanzi if "一" <= c <= "鿿" or "㐀" <= c <= "䶿"]
    out = list(tones)

    # 3-3 → 2-3 (left-to-right; a run of thirds becomes rising except the last).
    for i in range(len(out) - 1):
        if out[i] == 3 and out[i + 1] == 3:
            out[i] = 2

    # 不 (bù, base 4) → 2 before a 4th tone.
    # 一 (yī, base 1) → 2 before 4th tone, → 4 before 1/2/3.
    for i, ch in enumerate(han):
        if i >= len(out):
            break
        nxt = out[i + 1] if i + 1 < len(out) else None
        if ch == "不" and nxt == 4:
            out[i] = 2
        elif ch == "一":
            if nxt == 4:
                out[i] = 2
            elif nxt in (1, 2, 3):
                out[i] = 4
    return out


def verdict(expected_tone: int, detected_tone: int, confidence: float) -> dict:
    ok = expected_tone == detected_tone or expected_tone == 5
    return {
        "expected": expected_tone,
        "detected": detected_tone,
        "ok": ok,
        "confidence": round(confidence, 2),
    }
