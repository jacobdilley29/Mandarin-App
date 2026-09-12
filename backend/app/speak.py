"""Pronunciation scoring pipeline (spec §3.4).

Takes an uploaded recording (16-kHz mono WAV, decoded in the browser) plus the
target text, and returns:
  - transcription vs. target (when faster-whisper is available),
  - per-syllable tone verdicts (expected vs. detected, with sandhi applied),
  - contour points (the learner's pitch, normalised to semitones) and an
    idealised expected contour, for the SVG overlay.

Honest about being approximate — a "tone check", not a precise score.
"""

from __future__ import annotations

import numpy as np

from . import pitch, tone_classify, whisper_asr
from .tones import han_syllable_count, tones_from_pinyin

_HAN_LO, _HAN_HI = "一", "鿿"


def _han_chars(text: str) -> list[str]:
    return [c for c in text if _HAN_LO <= c <= _HAN_HI or "㐀" <= c <= "䶿"]


def _resample_16k(samples: np.ndarray, sr: int) -> np.ndarray:
    if sr == 16000:
        return samples
    n = int(round(samples.size * 16000 / sr))
    if n <= 1:
        return samples
    xp = np.linspace(0.0, 1.0, samples.size)
    x = np.linspace(0.0, 1.0, n)
    return np.interp(x, xp, samples).astype(np.float32)


# Idealised per-tone contour shapes, in semitones relative to the utterance
# median, sampled at u in [0, 1] across the syllable. Schematic (for the overlay).
_TEMPLATES = {
    1: lambda u: np.full_like(u, 3.0),
    2: lambda u: -2.0 + 6.0 * u,
    3: lambda u: -1.0 - 5.0 * np.sin(np.pi * np.clip(u, 0, 1)) + 4.0 * u,
    4: lambda u: 4.0 - 8.0 * u,
    5: lambda u: np.zeros_like(u),
}


def _syllable_bounds(
    times: np.ndarray, lo: int, hi: int, n_syll: int, asr: dict | None
) -> np.ndarray:
    """Frame indices splitting the voiced span into syllables.

    Prefers Whisper's word timestamps; falls back to equal slices when they are
    absent or don't line up with the expected syllable count.
    """
    equal = np.linspace(lo, hi, n_syll + 1).astype(int)
    words = (asr or {}).get("words") or []
    if not words:
        return equal

    # A Chinese "word" from Whisper may hold several characters; split its span
    # evenly across them, which is a far better guess than splitting the whole
    # utterance evenly.
    starts: list[float] = []
    ends: list[float] = []
    for w in words:
        chars = _han_chars(w.get("word", ""))
        n = len(chars) or 1
        w0, w1 = float(w.get("start", 0.0)), float(w.get("end", 0.0))
        if w1 <= w0:
            continue
        step = (w1 - w0) / n
        for i in range(n):
            starts.append(w0 + i * step)
            ends.append(w0 + (i + 1) * step)

    if len(starts) != n_syll:
        return equal

    edges = [starts[0]] + [(ends[i] + starts[i + 1]) / 2 for i in range(n_syll - 1)] + [ends[-1]]
    idx = np.searchsorted(times, np.asarray(edges)).astype(int)
    idx = np.clip(idx, lo, hi)
    # Monotonic and non-degenerate, or the slices below index backwards.
    if not np.all(np.diff(idx) > 0):
        return equal
    return idx


def _voiced_span(times: np.ndarray, f0: np.ndarray) -> tuple[int, int]:
    voiced = np.where(~np.isnan(f0))[0]
    if voiced.size == 0:
        return 0, len(f0)
    return int(voiced[0]), int(voiced[-1]) + 1


def _used_word_timings(bounds: np.ndarray, lo: int, hi: int, n_syll: int) -> bool:
    """Whether the bounds came from timestamps rather than even division."""
    equal = np.linspace(lo, hi, n_syll + 1).astype(int)
    return not np.array_equal(np.asarray(bounds), equal)


def score(audio_wav: bytes, target_hanzi: str, target_pinyin: str) -> dict:
    samples, sr = pitch.read_wav(audio_wav)
    times, f0 = pitch.extract_f0(samples, sr)

    chars = _han_chars(target_hanzi)
    n_syll = len(chars) or han_syllable_count(target_hanzi) or 1
    base_tones = tones_from_pinyin(target_pinyin)
    # Align tone list to syllable count as best we can.
    if len(base_tones) < n_syll:
        base_tones = base_tones + [5] * (n_syll - len(base_tones))
    base_tones = base_tones[:n_syll]
    expected = tone_classify.apply_sandhi(target_hanzi, base_tones)

    # Transcription (optional).
    asr = whisper_asr.transcribe(_resample_16k(samples, sr))
    transcript = asr["text"] if asr else None
    transcript_chars = _han_chars(transcript) if transcript else []

    # Normalise the whole utterance to semitones relative to its median.
    voiced_vals = f0[~np.isnan(f0)]
    median = float(np.median(voiced_vals)) if voiced_vals.size else 0.0
    st = np.where(np.isnan(f0), np.nan, 12.0 * np.log2(np.where(f0 > 0, f0, np.nan) / median)) if median > 0 else f0 * np.nan

    # Segment the utterance into per-syllable spans. Whisper's word timestamps
    # are used when available: equal-time slicing assumes every syllable takes
    # the same length, which a fourth tone followed by a drawled 嗎 plainly does
    # not, and a misplaced boundary classifies the wrong stretch of pitch.
    lo, hi = _voiced_span(times, f0)
    bounds = _syllable_bounds(times, lo, hi, n_syll, asr)

    syllables = []
    for i in range(n_syll):
        seg = f0[bounds[i] : bounds[i + 1]]
        # Classify on the stable core of the syllable — frames near a boundary
        # straddle two syllables (the analysis window overlaps both), so trim
        # ~20% from each end when the segment is long enough.
        m = int(len(seg) * 0.2)
        core = seg[m : len(seg) - m] if len(seg) - 2 * m >= 3 else seg
        detected, conf = tone_classify.classify_contour(core)
        v = tone_classify.verdict(expected[i], detected, conf)
        v["index"] = i
        v["char"] = chars[i] if i < len(chars) else None
        if transcript_chars:
            heard = transcript_chars[i] if i < len(transcript_chars) else None
            v["heard"] = heard
            v["char_ok"] = (heard == v["char"]) if v["char"] else None
        syllables.append(v)

    # Contour points for the SVG (voiced only), x in [0,1] across the utterance.
    total = max(1, len(f0) - 1)
    points = [
        {"x": round(idx / total, 4), "y": round(float(st[idx]), 3)}
        for idx in range(len(f0))
        if not np.isnan(st[idx])
    ]

    # Idealised expected contour, one template per syllable across [0,1].
    expected_contour: list[dict] = []
    for i in range(n_syll):
        u = np.linspace(0.0, 1.0, 8)
        y = _TEMPLATES.get(expected[i], _TEMPLATES[5])(u)
        x0 = i / n_syll
        for uu, yy in zip(u, y):
            expected_contour.append({"x": round(x0 + uu / n_syll, 4), "y": round(float(yy), 3)})

    syllable_bounds = [round((bounds[i] - lo) / max(1, hi - lo), 4) for i in range(n_syll + 1)]
    correct = sum(1 for s in syllables if s["ok"])

    # Segmental accuracy (spec §3.5): did the right sounds come out, regardless
    # of tone. Only meaningful when transcription ran — otherwise it is reported
    # as None rather than silently scored as zero or as perfect.
    judged = [s for s in syllables if s.get("char_ok") is not None]
    segmental_correct = sum(1 for s in judged if s["char_ok"]) if judged else None
    segmental_total = len(judged) if judged else None

    return {
        "target": {"hanzi": target_hanzi, "pinyin": target_pinyin},
        # True when syllable boundaries were guessed by even division rather than
        # taken from transcription timings.
        "approximate": not _used_word_timings(bounds, lo, hi, n_syll),
        "whisper_available": asr is not None,
        "transcription": transcript,
        "syllables": syllables,
        "tone_correct": correct,
        "tone_total": n_syll,
        "segmental_correct": segmental_correct,
        "segmental_total": segmental_total,
        "contour": {"points": points, "syllable_bounds": syllable_bounds},
        "expected_contour": expected_contour,
        "median_hz": round(median, 1) if median else None,
    }
