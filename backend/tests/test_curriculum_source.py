"""Per-unit curriculum source files (spec §3.1)."""

from __future__ import annotations

import json

import pytest

from app import completeness, curriculum_source as cs


@pytest.fixture
def content_dir(tmp_path, monkeypatch):
    """Point the source loader at a throwaway content directory."""
    monkeypatch.setattr(cs, "CONTENT_DIR", tmp_path)
    monkeypatch.setattr(cs, "MANIFEST_PATH", tmp_path / "curriculum.json")
    monkeypatch.setattr(cs, "UNITS_DIR", tmp_path / "units")
    return tmp_path


def _unit(uid, sort_order=0, **kw):
    u = {"id": uid, "title": uid, "sort_order": sort_order,
         "lessons": [{"id": f"l_{uid}", "title": "L", "vocab": [], "sentences": []}]}
    u.update(kw)
    return u


# ---------------------------------------------------------------------------
# Split / merge
# ---------------------------------------------------------------------------
def test_split_then_load_round_trips(content_dir):
    data = {"meta": {"function_words": ["我", "要"]},
            "units": [_unit("u_a", 0), _unit("u_b", 1), _unit("u_c", 2)]}

    cs.split(data)

    assert cs.load() == data


def test_split_writes_one_file_per_unit(content_dir):
    cs.split({"meta": {}, "units": [_unit("u_a"), _unit("u_b", 1)]})

    assert sorted(p.name for p in cs.UNITS_DIR.glob("*.json")) == ["u_a.json", "u_b.json"]


def test_the_manifest_holds_only_order_not_content(content_dir):
    cs.split({"meta": {"schema": 1}, "units": [_unit("u_a"), _unit("u_b", 1)]})

    manifest = json.loads(cs.MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["units"] == ["u_a", "u_b"]
    assert manifest["meta"] == {"schema": 1}


def test_manifest_order_is_preserved_through_sort_order(content_dir):
    cs.split({"meta": {}, "units": [_unit("u_z", 0), _unit("u_a", 1)]})

    assert [u["id"] for u in cs.load()["units"]] == ["u_z", "u_a"]


def test_unit_files_end_with_a_newline(content_dir):
    """Diffs shouldn't show a spurious 'no newline at end of file'."""
    cs.split({"meta": {}, "units": [_unit("u_a")]})

    assert cs.unit_path("u_a").read_text(encoding="utf-8").endswith("}\n")


# ---------------------------------------------------------------------------
# Loading behaviour
# ---------------------------------------------------------------------------
def test_a_unit_file_missing_from_the_manifest_is_still_loaded(content_dir):
    """A freshly generated draft must not vanish for want of a manifest edit."""
    cs.split({"meta": {}, "units": [_unit("u_a")]})
    cs.write_unit(_unit("u_new", 5, status="draft"))

    assert [u["id"] for u in cs.load()["units"]] == ["u_a", "u_new"]


def test_a_manifest_entry_with_no_file_is_a_clear_error(content_dir):
    cs.split({"meta": {}, "units": [_unit("u_a")]})
    cs.unit_path("u_a").unlink()

    with pytest.raises(FileNotFoundError, match="u_a"):
        cs.load()


def test_the_pre_split_layout_still_loads(content_dir):
    """Both layouts are readable, so the split needed no flag day."""
    combined = {"meta": {}, "units": [_unit("u_a")]}
    cs.MANIFEST_PATH.write_text(json.dumps(combined), encoding="utf-8")

    assert not cs.is_split()
    assert cs.load() == combined


def test_load_live_excludes_drafts(content_dir):
    cs.split({"meta": {}, "units": [_unit("u_a"), _unit("u_d", 1, status="draft")]})

    assert [u["id"] for u in cs.load_live()["units"]] == ["u_a"]
    assert [u["id"] for u in cs.load()["units"]] == ["u_a", "u_d"]


def test_status_defaults_to_live(content_dir):
    assert cs.status_of({"id": "u"}) == cs.STATUS_LIVE
    assert cs.status_of({"id": "u", "status": "draft"}) == cs.STATUS_DRAFT


# ---------------------------------------------------------------------------
# The committed content
# ---------------------------------------------------------------------------
def test_the_repo_content_is_split():
    assert cs.is_split(), "content/units/ should hold the curriculum source"


def test_every_committed_unit_file_is_named_for_its_id():
    for path in cs.UNITS_DIR.glob("*.json"):
        assert json.loads(path.read_text(encoding="utf-8"))["id"] == path.stem


def test_the_committed_manifest_lists_every_unit_file():
    listed = set(cs.load_manifest()["units"])
    on_disk = {p.stem for p in cs.UNITS_DIR.glob("*.json")}
    assert listed == on_disk


def test_the_committed_curriculum_merges_and_leads_with_the_curated_units():
    data = cs.load()
    live = cs.load_live()

    assert data["units"][0]["id"] == "u_conv", "便利商店 leads the curriculum"
    assert len(live["units"]) == 14, "only the hand-authored units are taught"
    assert len(data["units"]) > 14, "the HSK skeleton should be staged alongside them"
    assert completeness.summary(live)["draft"] == 0, "nothing live may be incomplete"
