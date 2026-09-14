"""Audio pre-generation (spec §5 step 4).

Synthesis itself needs the network, so what is tested here is everything around
it: which clips get warmed, which units are in scope, and that an unreachable
TTS service degrades instead of failing the build.
"""

from __future__ import annotations

import asyncio

import pytest

from app import audio, curriculum_source as cs
from scripts import warm_audio


def _unit(uid, *, status=None, hanzi="水"):
    u = {
        "id": uid, "title": uid, "sort_order": 0,
        "lessons": [{
            "id": f"l_{uid}", "sort_order": 0,
            "vocab": [{"id": "v1", "traditional": hanzi,
                       "example": {"hanzi": f"我要{hanzi}。"}}],
            "grammar": [{"id": "g1", "examples": [{"hanzi": f"{hanzi}嗎"}]}],
            "sentences": [{"tokens": ["我", "要", hanzi]}],
            "dialogue": [{"hanzi": f"{hanzi}好"}],
        }],
    }
    if status:
        u["status"] = status
    return u


def test_every_playable_string_is_collected():
    found = dict(warm_audio.clips({"units": [_unit("u")]}))

    assert "水" in found and found["水"] == "vocab"
    assert "我要水。" in found and found["我要水。"] == "example"
    assert "水嗎" in found and found["水嗎"] == "grammar"
    assert "我要水" in found and found["我要水"] == "sentence"
    assert "水好" in found and found["水好"] == "dialogue"


def test_clips_are_deduplicated():
    """The same phrase in two lessons is one clip, not two."""
    items = warm_audio.clips({"units": [_unit("u_a"), _unit("u_b")]})
    texts = [t for t, _ in items]

    assert len(texts) == len(set(texts))


def test_drill_sentence_tokens_are_joined():
    items = dict(warm_audio.clips({"units": [_unit("u")]}))
    assert "我要水" in items, "tokens must be joined into a speakable sentence"


def test_empty_and_missing_fields_are_skipped():
    sparse = {"units": [{"id": "u", "lessons": [{"id": "l", "vocab": [
        {"id": "v", "traditional": "  ", "example": {}}]}]}]}
    assert warm_audio.clips(sparse) == []


def test_units_are_walked_in_curriculum_order():
    data = {"units": [_unit("u_b", hanzi="茶"), _unit("u_a", hanzi="水")]}
    data["units"][0]["sort_order"] = 2
    data["units"][1]["sort_order"] = 1

    first = warm_audio.clips(data)[0][0]
    assert first == "水", "warming should follow the order lessons are actually met"


def test_only_live_units_are_in_scope_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(cs, "CONTENT_DIR", tmp_path)
    monkeypatch.setattr(cs, "MANIFEST_PATH", tmp_path / "curriculum.json")
    monkeypatch.setattr(cs, "UNITS_DIR", tmp_path / "units")
    cs.split({"meta": {}, "units": [_unit("u_live"), _unit("u_draft", status="draft", hanzi="茶")]})

    live_texts = [t for t, _ in warm_audio.clips(cs.load_live())]
    all_texts = [t for t, _ in warm_audio.clips(cs.load())]

    assert "水" in live_texts and "茶" not in live_texts
    assert "茶" in all_texts


# ---------------------------------------------------------------------------
# Behaviour when the TTS service is unreachable
# ---------------------------------------------------------------------------
def test_an_unreachable_service_is_reported_not_raised(monkeypatch, tmp_path):
    async def boom(text, voice=None):
        raise audio.TTSUnavailable("no network")

    monkeypatch.setattr(audio, "get_or_create", boom)
    monkeypatch.setattr(audio, "cache_path", lambda t, v: tmp_path / f"{hash(t)}.mp3")

    stats = asyncio.run(warm_audio.warm([("水", "vocab")], [audio.DEFAULT_VOICE], False))

    assert stats["failed"] == 1 and stats["made"] == 0


def test_it_gives_up_once_it_is_clear_nothing_will_synthesise(monkeypatch, tmp_path):
    """Otherwise a warm run costs one network timeout per clip, hundreds of times."""
    calls = 0

    async def boom(text, voice=None):
        nonlocal calls
        calls += 1
        raise audio.TTSUnavailable("no network")

    monkeypatch.setattr(audio, "get_or_create", boom)
    monkeypatch.setattr(audio, "cache_path", lambda t, v: tmp_path / f"{abs(hash(t))}.mp3")

    items = [(f"字{i}", "vocab") for i in range(50)]
    asyncio.run(warm_audio.warm(items, [audio.DEFAULT_VOICE], False))

    assert calls < 10, f"gave up after {calls} failures, should be ~5"


def test_already_cached_clips_are_not_resynthesised(monkeypatch, tmp_path):
    cached = tmp_path / "hit.mp3"
    cached.write_bytes(b"x" * 100)

    async def boom(text, voice=None):
        raise AssertionError("should not synthesise a cached clip")

    monkeypatch.setattr(audio, "get_or_create", boom)
    monkeypatch.setattr(audio, "cache_path", lambda t, v: cached)

    stats = asyncio.run(warm_audio.warm([("水", "vocab")], [audio.DEFAULT_VOICE], False))

    assert stats["cached"] == 1 and stats["made"] == 0
    assert stats["bytes"] == 100


def test_dry_run_never_synthesises(monkeypatch, tmp_path):
    async def boom(text, voice=None):
        raise AssertionError("dry run must not call the service")

    monkeypatch.setattr(audio, "get_or_create", boom)
    monkeypatch.setattr(audio, "cache_path", lambda t, v: tmp_path / "nope.mp3")

    stats = asyncio.run(warm_audio.warm([("水", "vocab")], [audio.DEFAULT_VOICE], True))

    assert stats["made"] == 1 and stats["failed"] == 0


def test_the_committed_live_curriculum_has_clips_to_warm():
    items = warm_audio.clips(cs.load_live())
    assert len(items) > 300, f"only {len(items)} clips — did the live units shrink?"
