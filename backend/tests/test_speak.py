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


# ---------------------------------------------------------------------------
# Segmental accuracy and syllable segmentation (spec §3.5)
# ---------------------------------------------------------------------------
import io as _io
import wave as _wave

import numpy as _np

from app import speak as _speak


def _tone_wav(curve, dur=0.6, sr=16000):
    n = int(sr * dur)
    f0 = _np.interp(_np.linspace(0, 1, n), _np.linspace(0, 1, len(curve)), curve)
    sig = sum(_np.sin(k * 2 * _np.pi * _np.cumsum(f0) / sr) / k for k in range(1, 7))
    sig = (sig * _np.hanning(n) * 0.5).astype(_np.float32)
    buf = _io.BytesIO()
    with _wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((sig * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def test_third_tone_sandhi_is_applied_to_the_target():
    """你好 is nǐ hǎo on paper but ní hǎo in the mouth — scoring the written
    tones would mark a correct pronunciation wrong."""
    result = _speak.score(_tone_wav([110, 125, 145, 180, 110, 95, 80, 95]), "你好", "nǐ hǎo")

    assert [s["expected"] for s in result["syllables"]] == [2, 3]


def test_segmental_is_none_when_transcription_is_unavailable(monkeypatch):
    """Not zero and not perfect — the question simply wasn't asked."""
    monkeypatch.setattr(_speak.whisper_asr, "transcribe", lambda *a, **k: None)
    result = _speak.score(_tone_wav([110, 125, 145, 180]), "好", "hǎo")

    assert result["segmental_correct"] is None
    assert result["segmental_total"] is None
    assert result["whisper_available"] is False


def test_segmental_is_scored_when_transcription_runs(monkeypatch):
    monkeypatch.setattr(
        _speak.whisper_asr, "transcribe",
        lambda *a, **k: {"text": "你好", "words": [{"word": "你好", "start": 0.05, "end": 0.5}]},
    )
    result = _speak.score(_tone_wav([110, 125, 145, 180, 110, 95, 80, 95]), "你好", "nǐ hǎo")

    assert result["segmental_total"] == 2
    assert result["segmental_correct"] == 2
    assert result["transcription"] == "你好"


def test_a_wrong_sound_costs_segmental_but_not_necessarily_tone(monkeypatch):
    monkeypatch.setattr(
        _speak.whisper_asr, "transcribe",
        lambda *a, **k: {"text": "你貓", "words": [{"word": "你貓", "start": 0.05, "end": 0.5}]},
    )
    result = _speak.score(_tone_wav([110, 125, 145, 180, 110, 95, 80, 95]), "你好", "nǐ hǎo")

    assert result["segmental_correct"] == 1, "你 matched, 貓 did not"


def test_word_timings_are_used_for_syllable_boundaries(monkeypatch):
    """Equal-time slicing assumes every syllable is the same length; a fourth
    tone followed by a drawled 嗎 plainly isn't, and a misplaced boundary
    classifies the wrong stretch of pitch."""
    monkeypatch.setattr(
        _speak.whisper_asr, "transcribe",
        lambda *a, **k: {"text": "你好", "words": [
            {"word": "你", "start": 0.05, "end": 0.20},
            {"word": "好", "start": 0.25, "end": 0.55},
        ]},
    )
    result = _speak.score(_tone_wav([110, 125, 145, 180, 110, 95, 80, 95]), "你好", "nǐ hǎo")

    assert result["approximate"] is False


def test_equal_time_segmentation_is_flagged_as_approximate(monkeypatch):
    monkeypatch.setattr(_speak.whisper_asr, "transcribe", lambda *a, **k: None)
    result = _speak.score(_tone_wav([110, 125, 145, 180, 110, 95, 80, 95]), "你好", "nǐ hǎo")

    assert result["approximate"] is True


def test_mismatched_timing_counts_fall_back_to_equal_slices(monkeypatch):
    """Whisper hearing three syllables for a two-syllable target must not
    produce bounds that index backwards."""
    monkeypatch.setattr(
        _speak.whisper_asr, "transcribe",
        lambda *a, **k: {"text": "你好嗎", "words": [
            {"word": "你好嗎", "start": 0.05, "end": 0.55},
        ]},
    )
    result = _speak.score(_tone_wav([110, 125, 145, 180, 110, 95, 80, 95]), "你好", "nǐ hǎo")

    assert result["approximate"] is True
    assert len(result["syllables"]) == 2


def test_a_contour_is_always_returned_for_the_plot():
    result = _speak.score(_tone_wav([110, 125, 145, 180]), "好", "hǎo")

    assert result["contour"]["points"], "the pitch plot needs points to draw"
    assert result["expected_contour"], "and a reference contour to compare against"
    assert len(result["contour"]["syllable_bounds"]) == 2
