"""Fundamental-frequency (f0) extraction — pure numpy (spec §3.4).

An autocorrelation pitch tracker used to draw the learner's tone contour and to
classify tones. Deliberately dependency-light (numpy + stdlib `wave`) so it runs
without librosa/ffmpeg: the browser decodes the recording to 16-kHz mono WAV and
uploads that.
"""

from __future__ import annotations

import io
import wave

import numpy as np


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


def extract_f0(
    samples: np.ndarray,
    sr: int,
    fmin: float = 70.0,
    fmax: float = 400.0,
    frame_ms: float = 40.0,
    hop_ms: float = 10.0,
    voicing_threshold: float = 0.3,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (times, f0) per frame; f0 is NaN for unvoiced frames.

    Autocorrelation with parabolic interpolation of the peak lag.
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
