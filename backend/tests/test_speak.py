"""Tests for pronunciation scoring (spec §3.4, §7: tone classification)."""

from __future__ import annotations

import io
import wave

import numpy as np

from app import pitch, speak, tone_classify

SR = 16000


def _chao_hz(level: float) -> float:
    # Map Chao pitch level 1..5 to Hz over a ~roughly one-octave range.
    return 120.0 * (2.0 ** ((level - 1) * 3.5 / 12.0))


def synth_syllable(levels: list[float], dur: float = 0.45) -> np.ndarray:
    """A single syllable whose f0 traces the given Chao pitch levels."""
    t = np.linspace(0, 1, int(SR * dur), endpoint=False)
    f = np.interp(t, np.linspace(0, 1, len(levels)), [_chao_hz(l) for l in levels])
    return (0.5 * np.sin(2 * np.pi * np.cumsum(f) / SR)).astype(np.float32)


def to_wav(samples: np.ndarray) -> bytes:
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)
    return buf.getvalue()


# Canonical Chao contours per tone.
_SHAPES = {1: [5, 5], 2: [3, 5], 3: [2, 1, 4], 4: [5, 1]}


def test_read_wav_roundtrip():
    data = to_wav(synth_syllable([3, 3]))
    samples, sr = pitch.read_wav(data)
    assert sr == SR
    assert samples.size > 0
    assert -1.0 <= float(samples.min()) and float(samples.max()) <= 1.0


def test_extract_f0_recovers_known_pitch():
    # Steady 200 Hz tone → median f0 ≈ 200.
    samples = synth_syllable([_hz_to_level(200)] * 2) if False else None
    t = np.linspace(0, 0.4, int(SR * 0.4), endpoint=False)
    samples = (0.5 * np.sin(2 * np.pi * 200 * t)).astype(np.float32)
    _, f0 = pitch.extract_f0(samples, SR)
    med = pitch.median_f0(f0)
    assert med is not None
    assert abs(med - 200) < 10


def _hz_to_level(hz):  # pragma: no cover - helper stub for symmetry
    return 3


def test_classify_each_tone():
    for tone, shape in _SHAPES.items():
        _, f0 = pitch.extract_f0(synth_syllable(shape), SR)
        detected, conf = tone_classify.classify_contour(f0)
        assert detected == tone, f"tone {tone} misclassified as {detected}"
        assert 0.0 <= conf <= 1.0


def test_score_two_syllable_word_all_correct():
    # 便當 biàndāng = tones [4, 1]: falling + high-flat.
    audio = to_wav(np.concatenate([synth_syllable(_SHAPES[4]), synth_syllable(_SHAPES[1])]))
    result = speak.score(audio, "便當", "biàndāng")
    assert result["tone_total"] == 2
    assert result["approximate"] is True
    assert len(result["syllables"]) == 2
    assert [s["expected"] for s in result["syllables"]] == [4, 1]
    assert result["tone_correct"] == 2
    # Contour data present for the SVG overlay.
    assert result["contour"]["points"]
    assert result["expected_contour"]


def test_score_reports_wrong_tone():
    # Say [1, 1] where [4, 1] expected → first syllable flagged.
    audio = to_wav(np.concatenate([synth_syllable(_SHAPES[1]), synth_syllable(_SHAPES[1])]))
    result = speak.score(audio, "便當", "biàndāng")
    first = result["syllables"][0]
    assert first["expected"] == 4
    assert first["detected"] == 1
    assert first["ok"] is False


def test_score_applies_sandhi_to_expected():
    # 你好 nǐhǎo citation [3,3] → sandhi [2,3]; say a rising+dipping pair.
    audio = to_wav(np.concatenate([synth_syllable(_SHAPES[2]), synth_syllable(_SHAPES[3])]))
    result = speak.score(audio, "你好", "nǐhǎo")
    assert [s["expected"] for s in result["syllables"]] == [2, 3]


def test_sandhi_rules():
    assert tone_classify.apply_sandhi("你好", [3, 3]) == [2, 3]
    assert tone_classify.apply_sandhi("不是", [4, 4]) == [2, 4]
    assert tone_classify.apply_sandhi("一個", [1, 4]) == [2, 4]
    assert tone_classify.apply_sandhi("一天", [1, 1]) == [4, 1]
