"""HSK ↔ TOCFL ↔ CEFR level mapping (spec §3.1).

Jacob's exam track is TOCFL, so that is what the app shows him. The content is
sourced and graded by HSK — that is a sourcing detail, kept as the secondary
label rather than the headline.

The mapping is data (content/tocfl_mapping.json), not code, so a correction is a
content diff. This module is the only place that reads it, so every surface
labels a level the same way.

One caveat carried from the mapping file and worth repeating wherever this is
used: TOCFL's own vocabulary targets run ahead of HSK 2.0 at every band — TOCFL
Level 3 expects ~2,500 words against HSK 4's 1,200 cumulative. So finishing HSK 4
here covers TOCFL Level 3's themes and grammar but roughly half its vocabulary.
UI copy says "aligned to", never "covers".
"""

from __future__ import annotations

import json
from functools import lru_cache

from .config import REPO_ROOT

MAPPING_PATH = REPO_ROOT / "content" / "tocfl_mapping.json"

BANDS: tuple[int, ...] = (1, 2, 3, 4)


@lru_cache(maxsize=1)
def _mapping() -> dict:
    if not MAPPING_PATH.is_file():
        return {"meta": {}, "levels": []}
    return json.loads(MAPPING_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _by_hsk() -> dict[int, dict]:
    return {lv["hsk_level"]: lv for lv in _mapping().get("levels", [])}


def band(hsk_level: int | None) -> dict:
    """Everything the UI needs to label one level.

    Unknown or missing levels return a usable shape rather than raising: a
    vocabulary item with no hsk_level should render as "—", not crash a screen.
    """
    entry = _by_hsk().get(hsk_level or 0)
    if not entry:
        return {
            "hsk_level": hsk_level,
            "tocfl_level": None,
            "tocfl_level_zh": None,
            "tocfl_band": None,
            "cefr": None,
            "label": "—",
            "label_zh": "—",
            "sublabel": f"HSK {hsk_level}" if hsk_level else "",
        }
    return {
        "hsk_level": entry["hsk_level"],
        "tocfl_level": entry["tocfl_level"],
        "tocfl_level_zh": entry["tocfl_level_zh"],
        "tocfl_band": entry["tocfl_band"],
        "cefr": entry["cefr"],
        "tocfl_target_words": entry.get("tocfl_target_words"),
        "cumulative_words": entry.get("cumulative"),
        # What the UI prints: TOCFL first, HSK as the smaller second line.
        "label": entry["tocfl_level"],
        "label_zh": entry["tocfl_level_zh"],
        "sublabel": f"HSK {entry['hsk_level']}",
    }


def all_bands() -> list[dict]:
    return [band(level) for level in BANDS]


def caveat() -> str:
    return _mapping().get("meta", {}).get("caveat", "")
