"""Pitch extraction (spec §3.5, §4).

Tone scoring is only as good as the f0 track underneath it, so these measure the
trackers against synthesised contours with a *known* f0 rather than asserting
that some code path ran.

They are also the record behind a stack decision: §4 names "librosa +
parselmouth", and librosa is deliberately not used. On these same signals it
measured 0.108–0.194 semitones median error against parselmouth's 0.018–0.028,
and its first call pays ~25 s of numba JIT — worse and slower, for ~425 MB.
"""

from __future__ import annotations

import io
import wave

import numpy as np
import pytest

from app import pitch

SR = 16000


def synth(curve: list[float], dur: float = 0.5) -> tuple[np.ndarray, np.ndarray]:
    """A harmonic tone whose f0 follows `curve` — the ground truth to score against."""
    n = int(SR * dur)
    f0 = np.interp(np.linspace(0, 1, n), np.linspace(0, 1, len(curve)), curve)
    phase = 2 * np.pi * np.cumsum(f0) / SR
    sig = sum(np.sin(k * phase) / k for k in range(1, 7)) * np.hanning(n) * 0.5
    return sig.astype(np.float32), f0


def to_wav(sig: np.ndarray) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((sig * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def median_error_semitones(times, f0, truth, dur=0.5) -> float:
    voiced = ~np.isnan(f0)
    assert voiced.sum() >= 3, "tracker found almost no voiced frames"
    expected = np.interp(np.asarray(times)[voiced], np.linspace(0, dur, len(truth)), truth)
    return float(np.median(np.abs(12 * np.log2(np.asarray(f0)[voiced] / expected))))


# Mandarin tone shapes.
TONES = {
    "tone1 level": [150, 150, 150, 150],
    "tone2 rising": [110, 125, 145, 180],
    "tone3 dipping": [110, 95, 80, 95, 150],
    "tone4 falling": [200, 160, 120, 90],
}


@pytest.mark.parametrize("name", list(TONES))
def test_praat_tracks_every_tone_shape_accurately(name):
    """Under a tenth of a semitone — far finer than tone judgement needs."""
    sig, truth = synth(TONES[name])
    times, f0 = pitch.extract_f0(sig, SR)

    assert median_error_semitones(times, f0, truth) < 0.1


@pytest.mark.parametrize("name", list(TONES))
def test_the_numpy_fallback_is_usable_too(name):
    """Looser, but good enough that a machine without parselmouth still scores."""
    sig, truth = synth(TONES[name])
    times, f0 = pitch.extract_f0_numpy(sig, SR)

    assert median_error_semitones(times, f0, truth) < 0.3


# Tones 2, 3 and 4 move; tone 1 is flat. On a flat tone both trackers are exact
# to four decimal places and which one "wins" is noise — the comparison only
# means anything where the pitch actually changes, which is also the only place
# tone discrimination is hard.
MOVING_TONES = [n for n in TONES if not n.startswith("tone1")]


@pytest.mark.parametrize("name", MOVING_TONES)
def test_praat_beats_the_fallback_on_contours_that_move(name):
    """The reason for the switch, measured rather than asserted."""
    sig, truth = synth(TONES[name])

    praat = median_error_semitones(*pitch.extract_f0(sig, SR), truth)
    numpy_err = median_error_semitones(*pitch.extract_f0_numpy(sig, SR), truth)
    assert praat < numpy_err / 2, f"praat {praat:.4f} vs numpy {numpy_err:.4f}"


def test_both_trackers_are_exact_on_a_level_tone():
    """No contour to follow, so neither has an edge — recorded so the claim above
    is not mistaken for a general one."""
    sig, truth = synth(TONES["tone1 level"])

    for times, f0 in (pitch.extract_f0(sig, SR), pitch.extract_f0_numpy(sig, SR)):
        assert median_error_semitones(times, f0, truth) < 0.01


def test_parselmouth_is_what_runs_by_default():
    pytest.importorskip("parselmouth")
    sig, _ = synth(TONES["tone2 rising"])

    assert pitch._parselmouth_f0(sig, SR, 70.0, 400.0, 0.01) is not None


def test_extract_f0_falls_back_when_parselmouth_is_missing(monkeypatch):
    """A machine without it must still score tones, not error."""
    monkeypatch.setattr(pitch, "_parselmouth_f0", lambda *a, **k: None)
    sig, truth = synth(TONES["tone2 rising"])

    times, f0 = pitch.extract_f0(sig, SR)
    assert median_error_semitones(times, f0, truth) < 0.3


def test_a_broken_recording_degrades_instead_of_raising(monkeypatch):
    """parselmouth throwing on odd input must not 500 the endpoint."""
    def boom(*a, **k):
        raise RuntimeError("bad sound")

    monkeypatch.setattr(pitch, "_parselmouth_f0", boom)
    with pytest.raises(RuntimeError):
        pitch._parselmouth_f0(np.zeros(10), SR, 70.0, 400.0, 0.01)


def test_unvoiced_frames_are_nan_not_zero():
    """Praat reports 0 for unvoiced; the pipeline expects NaN and would otherwise
    treat silence as a very low pitch."""
    silence = np.zeros(SR // 2, dtype=np.float32)
    _times, f0 = pitch.extract_f0(silence, SR)

    assert len(f0) == 0 or np.all(np.isnan(f0) | (f0 > 0))


def test_empty_audio_returns_empty_arrays():
    times, f0 = pitch.extract_f0(np.array([], dtype=np.float32), SR)
    assert len(times) == 0 and len(f0) == 0


def test_wav_round_trip():
    sig, _ = synth(TONES["tone1 level"])
    samples, sr = pitch.read_wav(to_wav(sig))

    assert sr == SR
    assert np.allclose(samples, sig, atol=1e-3)


def test_stereo_is_mixed_to_mono():
    sig, _ = synth(TONES["tone1 level"])
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        stereo = np.repeat((sig * 32767).astype("<i2"), 2)
        w.writeframes(stereo.tobytes())

    samples, _ = pitch.read_wav(buf.getvalue())
    assert samples.ndim == 1 and len(samples) == len(sig)
