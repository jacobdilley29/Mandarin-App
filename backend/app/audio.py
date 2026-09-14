"""Text-to-speech via edge-tts, cached to disk (spec §2, §5).

The two Taiwan voices (zh-TW-HsiaoChenNeural / zh-TW-YunJheNeural) are used
throughout. Generated mp3s are cached under data/audio/ keyed by (voice, text),
so each phrase is synthesised at most once.

Playback speed is handled in the browser (Web Audio), so it is not part of the
cache key — one clip serves every speed.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path

from .config import get_settings

VOICES = {"zh-TW-HsiaoChenNeural", "zh-TW-YunJheNeural"}
DEFAULT_VOICE = "zh-TW-HsiaoChenNeural"

# Serialise generation of the same key to avoid duplicate work / partial files.
_locks: dict[str, asyncio.Lock] = {}


class TTSUnavailable(RuntimeError):
    """Raised when a clip could not be generated (e.g. no network)."""


def cache_path(text: str, voice: str) -> Path:
    key = hashlib.sha256(f"{voice}\n{text}".encode("utf-8")).hexdigest()[:20]
    return get_settings().audio_dir / f"{key}.mp3"


async def get_or_create(text: str, voice: str | None = None) -> Path:
    text = (text or "").strip()
    if not text:
        raise TTSUnavailable("empty text")
    voice = voice if voice in VOICES else DEFAULT_VOICE

    path = cache_path(text, voice)
    if path.is_file() and path.stat().st_size > 0:
        return path

    lock = _locks.setdefault(str(path), asyncio.Lock())
    async with lock:
        # Re-check after acquiring the lock (another request may have made it).
        if path.is_file() and path.stat().st_size > 0:
            return path
        await _synthesize(text, voice, path)
    return path


async def _synthesize(text: str, voice: str, path: Path) -> None:
    try:
        import edge_tts
    except ImportError as e:  # pragma: no cover - dependency guard
        raise TTSUnavailable("edge-tts not installed") from e

    get_settings().ensure_dirs()
    tmp = path.with_suffix(".part")
    # Honour an HTTPS proxy if one is configured (harmless when unset).
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    try:
        communicate = edge_tts.Communicate(text, voice, proxy=proxy)
        await communicate.save(str(tmp))
        if not tmp.is_file() or tmp.stat().st_size == 0:
            raise TTSUnavailable("edge-tts produced no audio")
        os.replace(tmp, path)
    except TTSUnavailable:
        raise
    except Exception as e:  # network / DRM / connection errors
        raise TTSUnavailable(f"edge-tts failed: {e}") from e
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
