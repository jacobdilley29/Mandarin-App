"""Curriculum source files: one JSON file per unit (spec §3.1).

The spec asks for curriculum content to live as "structured, versioned source
data ... one YAML/JSON file per unit ... kept separate from application code",
so that reorganising or correcting the curriculum is a reviewable content diff
rather than a change buried in app logic or a database migration.

Layout:

    content/curriculum.json     manifest — meta, function_words, unit order
    content/units/<unit_id>.json    one unit: its lessons, vocab, grammar,
                                    dialogue, drill sentences, and status

`load()` merges them back into exactly the shape the rest of the app already
consumes — the same dict `validate_curriculum()` and `content.load_curriculum()`
took when this was one file — so neither the validator nor the DB loader needed
to change for the split.

A unit file also carries `status`: "live" units are taught, "draft" units are
staged but withheld from the Learn map until they are complete. See
app/completeness.py for what completeness means and why the gate exists.
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import REPO_ROOT

CONTENT_DIR = REPO_ROOT / "content"
MANIFEST_PATH = CONTENT_DIR / "curriculum.json"
UNITS_DIR = CONTENT_DIR / "units"

STATUS_LIVE = "live"
STATUS_DRAFT = "draft"


def unit_path(unit_id: str) -> Path:
    return UNITS_DIR / f"{unit_id}.json"


def is_split() -> bool:
    """True once the curriculum has been split into per-unit files.

    Both layouts are readable so the split can land without a flag day, and so a
    branch that predates it still loads.
    """
    return UNITS_DIR.is_dir() and any(UNITS_DIR.glob("*.json"))


def load_manifest() -> dict:
    if not MANIFEST_PATH.is_file():
        return {"meta": {}, "units": []}
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def load_unit(unit_id: str) -> dict:
    return json.loads(unit_path(unit_id).read_text(encoding="utf-8"))


def load() -> dict:
    """The whole curriculum, in the combined in-memory shape the app expects.

    Reads either layout, discriminating on the shape of the manifest's `units`
    rather than on what happens to be in content/units/: a list of dicts is a
    pre-split combined file, a list of ids is a manifest. Going by the directory
    listing would mean a manifest whose unit files had all been deleted silently
    loaded as a combined curriculum, handing every caller unit *strings* instead
    of raising.
    """
    manifest = load_manifest()
    order = manifest.get("units") or []

    if order and isinstance(order[0], dict):
        # Pre-split layout: curriculum.json already holds everything.
        return manifest

    if not order and not is_split():
        # Nothing anywhere — an empty curriculum, not an error.
        return {"meta": manifest.get("meta", {}), "units": []}

    units = []
    for unit_id in order:
        path = unit_path(unit_id)
        if not path.is_file():
            raise FileNotFoundError(
                f"curriculum.json lists unit {unit_id!r} but {path} does not exist"
            )
        units.append(load_unit(unit_id))

    # Any unit file not named in the manifest is still loaded, after the ordered
    # ones — a newly generated draft shouldn't vanish just because nobody has
    # added it to the manifest yet.
    listed = set(order)
    for path in sorted(UNITS_DIR.glob("*.json")):
        if path.stem not in listed:
            units.append(load_unit(path.stem))

    units.sort(key=lambda u: (u.get("sort_order", 0), u.get("id", "")))
    return {"meta": manifest.get("meta", {}), "units": units}


def load_live() -> dict:
    """Only the units cleared for teaching. Drafts are excluded entirely."""
    data = load()
    return {
        "meta": data.get("meta", {}),
        "units": [u for u in data.get("units", []) if status_of(u) == STATUS_LIVE],
    }


def status_of(unit: dict) -> str:
    """A unit's status, defaulting to live.

    Defaulting to live keeps the hand-authored units — written before statuses
    existed — taught without needing to be touched. Anything the pipeline
    generates sets `status` explicitly, and sets it to draft.
    """
    return unit.get("status", STATUS_LIVE)


def write_unit(unit: dict, *, indent: int = 2) -> Path:
    """Write one unit file. Sorted, newline-terminated: made to diff cleanly."""
    UNITS_DIR.mkdir(parents=True, exist_ok=True)
    path = unit_path(unit["id"])
    path.write_text(
        json.dumps(unit, ensure_ascii=False, indent=indent) + "\n", encoding="utf-8"
    )
    return path


def write_manifest(meta: dict, unit_ids: list[str], *, indent: int = 2) -> Path:
    MANIFEST_PATH.write_text(
        json.dumps({"meta": meta, "units": unit_ids}, ensure_ascii=False, indent=indent) + "\n",
        encoding="utf-8",
    )
    return MANIFEST_PATH


def split(data: dict) -> tuple[Path, list[Path]]:
    """Write a combined curriculum out as a manifest plus one file per unit."""
    units = sorted(data.get("units", []), key=lambda u: u.get("sort_order", 0))
    paths = [write_unit(u) for u in units]
    manifest = write_manifest(data.get("meta", {}), [u["id"] for u in units])
    return manifest, paths
