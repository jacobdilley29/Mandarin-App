"""faster-whisper wrapper (spec §2, §3.4) — lazy and optional.

Transcription and word timestamps improve per-syllable segmentation, but the
tone analysis degrades gracefully without them (equal-time segmentation). The
model is loaded lazily and cached; if faster-whisper or its model isn't
available, `transcribe` returns None and the rest of the pipeline continues.
"""

from __future__ import annotations

import numpy as np

from .config import get_settings

_model = None
_load_failed = False


def available() -> bool:
    """Whether transcription can run (model loads successfully)."""
    return _get_model() is not None


def _get_model():
    global _model, _load_failed
    if _model is not None or _load_failed:
        return _model
    try:
        from faster_whisper import WhisperModel

        size = get_settings().whisper_model
        _model = WhisperModel(size, device="cpu", compute_type="int8")
    except Exception:
        # Not installed, model not downloaded, or load error — degrade quietly.
        _load_failed = True
        _model = None
    return _model


def transcribe(samples: np.ndarray) -> dict | None:
    """Transcribe 16-kHz mono float32 audio.

    Returns {text, words:[{word,start,end}]} or None if unavailable.
    """
    model = _get_model()
    if model is None:
        return None
    try:
        segments, _info = model.transcribe(
            samples.astype(np.float32),
            language="zh",
            word_timestamps=True,
            vad_filter=False,
        )
        text_parts: list[str] = []
        words: list[dict] = []
        for seg in segments:
            text_parts.append(seg.text)
            for w in seg.words or []:
                words.append({"word": w.word.strip(), "start": w.start, "end": w.end})
        return {"text": "".join(text_parts).strip(), "words": words}
    except Exception:
        return None
