"""Fundamental-frequency (f0) extraction (spec §3.5).

Tone scoring is only as good as the pitch track underneath it, so this uses
**Praat** via parselmouth — the same algorithm phoneticians use, reached through
a thin binding rather than reimplemented.

Measured against synthesised tone contours with known f0 (see
tests/test_pitch.py), on Mandarin tones 2, 3 and 4:

    parselmouth      0.018-0.028 semitones median error,  1-2 ms
    numpy fallback   0.056-0.085 semitones median error,  5-6 ms
    librosa pyin     0.108-0.194 semitones median error, 73 ms+

librosa is named in the spec alongside parselmouth but is deliberately **not**
used: it measured worst on accuracy and slowest by an order of magnitude here
(pyin is built for music, and its first call pays a numba JIT cost of ~25 s),
and it would add ~425 MB to the image for a worse result. Discussed and agreed
rather than quietly substituted.

The numpy autocorrelation tracker is kept as a fallback so a machine without
parselmouth still scores tones — it is accurate enough to be useful, just less
so. Both take the same 16-kHz mono WAV the browser uploads, so neither needs
ffmpeg.
"""

from __future__ import annotations

import io
import logging
import wave

import numpy as np

log = logging.getLogger(__name__)

# Praat's defaults are tuned for speech; these bound a learner's voice range.
PITCH_FLOOR = 70.0
PITCH_CEILING = 400.0
TIME_STEP = 0.01  # 10 ms frames, matching the fallback's hop


def read_wav(data: bytes) -> tuple[np.ndarray, int]:
    """Read a mono/stereo 16-bit PCM WAV into float32 samples in [-1, 1]."""
    with wave.open(io.BytesIO(data), "rb") as w:
        n_channels = w.getnchannels()
        sr = w.getframerate()
        width = w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if width != 2:
        raise ValueError("only 16-bit PCM WAV is supported")
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    if n_channels > 1:
        samples = samples.reshape(-1, n_channels).mean(axis=1)
    return samples, sr


def tracker_name() -> str:
    """Which pitch tracker this install will actually use.

    Reported by /api/status so a machine quietly running the fallback — an
    Apple Silicon Docker image, where Praat has no wheel — says so instead of
    looking identical to one running Praat.
    """
    try:
        import parselmouth  # noqa: F401
    except ImportError:
        return "numpy"
    return "praat"


def _parselmouth_f0(
    samples: np.ndarray, sr: int, fmin: float, fmax: float, time_step: float
) -> tuple[np.ndarray, np.ndarray] | None:
    """Praat's pitch track, or None when parselmouth isn't installed.

    Imported lazily: the module is only needed when someone actually records,
    and the app must start on a machine that never installed it.
    """
    try:
        import parselmouth
    except ImportError:
        return None

    try:
        sound = parselmouth.Sound(samples.astype(np.float64), sampling_frequency=sr)
        pitch = sound.to_pitch(time_step=time_step, pitch_floor=fmin, pitch_ceiling=fmax)
    except Exception as exc:  # noqa: BLE001 — a bad recording must not 500
        log.warning("parselmouth pitch extraction failed (%s); using the fallback", exc)
        return None

    freqs = np.asarray(pitch.selected_array["frequency"], dtype=float)
    # Praat reports unvoiced frames as 0; the rest of the pipeline expects NaN.
    freqs = np.where(freqs <= 0, np.nan, freqs)
    return np.asarray(pitch.xs(), dtype=float), freqs


def extract_f0(
    samples: np.ndarray,
    sr: int,
    fmin: float = PITCH_FLOOR,
    fmax: float = PITCH_CEILING,
    frame_ms: float = 40.0,
    hop_ms: float = 10.0,
    voicing_threshold: float = 0.3,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (times, f0) per frame; f0 is NaN for unvoiced frames.

    Praat via parselmouth when available, else the numpy autocorrelation tracker
    below. Both return the same shape, so callers never need to know which ran.
    """
    if samples.size == 0:
        return np.array([]), np.array([])

    praat = _parselmouth_f0(samples, sr, fmin, fmax, hop_ms / 1000.0)
    if praat is not None:
        return praat

    return extract_f0_numpy(samples, sr, fmin, fmax, frame_ms, hop_ms, voicing_threshold)


def extract_f0_numpy(
    samples: np.ndarray,
    sr: int,
    fmin: float = PITCH_FLOOR,
    fmax: float = PITCH_CEILING,
    frame_ms: float = 40.0,
    hop_ms: float = 10.0,
    voicing_threshold: float = 0.3,
) -> tuple[np.ndarray, np.ndarray]:
    """Autocorrelation tracker with parabolic interpolation of the peak lag.

    The fallback when parselmouth is unavailable, and the reference the tests
    compare Praat against.
    """
    if samples.size == 0:
        return np.array([]), np.array([])

    frame = int(sr * frame_ms / 1000)
    hop = int(sr * hop_ms / 1000)
    min_lag = max(1, int(sr / fmax))
    max_lag = min(frame - 1, int(sr / fmin))

    times: list[float] = []
    f0s: list[float] = []
    for start in range(0, max(1, samples.size - frame + 1), hop):
        seg = samples[start : start + frame]
        if seg.size < frame:
            break
        seg = seg - seg.mean()
        energy = float(np.dot(seg, seg))
        t = (start + frame / 2) / sr

        if energy < 1e-6:
            times.append(t)
            f0s.append(np.nan)
            continue

        # Autocorrelation via FFT (linear, zero-padded).
        nfft = 1 << int(np.ceil(np.log2(2 * frame)))
        spec = np.fft.rfft(seg, nfft)
        corr = np.fft.irfft(spec * np.conj(spec), nfft)[: frame]

        lag_slice = corr[min_lag : max_lag + 1]
        if lag_slice.size == 0:
            times.append(t)
            f0s.append(np.nan)
            continue

        peak = int(np.argmax(lag_slice)) + min_lag
        # Voicing: normalised autocorrelation peak strength.
        if corr[0] <= 0 or corr[peak] / corr[0] < voicing_threshold:
            times.append(t)
            f0s.append(np.nan)
            continue

        # Parabolic interpolation around the peak for sub-sample accuracy.
        if 0 < peak < frame - 1:
            a, b, c = corr[peak - 1], corr[peak], corr[peak + 1]
            denom = a - 2 * b + c
            shift = 0.5 * (a - c) / denom if denom != 0 else 0.0
        else:
            shift = 0.0
        lag = peak + shift
        f0 = sr / lag if lag > 0 else np.nan
        times.append(t)
        f0s.append(f0 if fmin <= f0 <= fmax else np.nan)

    return np.array(times), np.array(f0s)


def median_f0(f0: np.ndarray) -> float | None:
    voiced = f0[~np.isnan(f0)]
    return float(np.median(voiced)) if voiced.size else None
