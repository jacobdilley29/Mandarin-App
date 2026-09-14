"""Importing an official TOCFL vocabulary list (source data for the curriculum).

The app's units are built from HSK lists with TOCFL labels mapped over them, and
content/tocfl_mapping.json says plainly what that costs: TOCFL Level 3 expects
~2,500 words against HSK 4's 1,200 cumulative. Swapping the source list is the
change that closes the gap, and this importer is the way in.

Every export is shaped differently, so these tests pin the tolerance: Chinese or
English headers, comma or tab, a missing pinyin column, a stray Simplified
entry, junk rows. Nothing here needs a network or an API key.
"""

from __future__ import annotations

import json

import pytest

from scripts import import_tocfl as it

NOVICE = "\n".join([
    "詞語,拼音,英文",
    "水,shuǐ,water",
    "茶,chá,tea",
    "朋友,péngyǒu,friend",
])


def _write(tmp_path, text, name="list.csv"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Reading whatever the export looks like
# ---------------------------------------------------------------------------
def test_chinese_headers_are_understood(tmp_path):
    words, _ = it.parse(_write(tmp_path, NOVICE), "novice")

    assert [w["traditional"] for w in words] == ["水", "茶", "朋友"]
    assert words[0]["gloss"] == "water"


def test_english_headers_work_too(tmp_path):
    csv = "Word,Pinyin,English\n水,shuǐ,water\n"

    words, _ = it.parse(_write(tmp_path, csv), "novice")
    assert words[0]["traditional"] == "水"


def test_a_decorated_header_still_matches(tmp_path):
    """Real exports say things like 漢語拼音(Pinyin), not a bare keyword."""
    csv = "生詞,漢語拼音(Pinyin),英文解釋 / English\n水,shuǐ,water\n"

    words, _ = it.parse(_write(tmp_path, csv), "novice")
    assert words[0]["pinyin"] and words[0]["gloss"] == "water"


def test_tab_separated_is_detected(tmp_path):
    words, _ = it.parse(_write(tmp_path, "詞語\t拼音\t英文\n水\tshuǐ\twater\n", name="l.tsv"), "1")
    assert words[0]["traditional"] == "水"


def test_a_file_with_no_word_column_fails_loudly(tmp_path):
    """Better to stop with the header printed than to import nothing quietly."""
    with pytest.raises(SystemExit, match="could not find a word column"):
        it.parse(_write(tmp_path, "foo,bar\n1,2\n"), "1")


# ---------------------------------------------------------------------------
# Taiwan normalisation — the reason this doesn't just read the CSV
# ---------------------------------------------------------------------------
def test_a_missing_pinyin_column_is_derived(tmp_path):
    words, _ = it.parse(_write(tmp_path, "詞語,英文\n茶,tea\n"), "novice")

    assert words[0]["pinyin"] == "chá"


def test_taiwan_readings_override_the_file(tmp_path):
    """垃圾 is lèsè here. A mainland-standard export must not set the app's readings."""
    words, notes = it.parse(_write(tmp_path, "詞語,拼音,英文\n垃圾,lā jī,rubbish\n"), "1")

    assert words[0]["pinyin"] == "lèsè"
    assert any("垃圾" in n for n in notes), "an overridden reading should be reported"


def test_a_simplified_stray_is_converted(tmp_path):
    words, _ = it.parse(_write(tmp_path, "詞語,英文\n学生,student\n"), "1")

    assert words[0]["traditional"] == "學生"


def test_junk_rows_are_skipped_not_imported(tmp_path):
    csv = "詞語,英文\n水,water\n(以下空白),\n總計 300 詞,\n茶,tea\n"

    words, notes = it.parse(_write(tmp_path, csv), "1")
    assert [w["traditional"] for w in words] == ["水", "茶"]
    assert any("skipped" in n for n in notes)


def test_duplicates_within_a_file_collapse(tmp_path):
    words, _ = it.parse(_write(tmp_path, "詞語,英文\n水,water\n水,water again\n"), "1")
    assert len(words) == 1


def test_file_order_is_preserved_as_frequency(tmp_path):
    """These lists are graded; the order is information, so keep it."""
    words, _ = it.parse(_write(tmp_path, NOVICE), "novice")
    assert [w["frequency"] for w in words] == [1, 2, 3]


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------
def test_dry_run_writes_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(it, "WORDLISTS", tmp_path / "out")

    assert it.main([str(_write(tmp_path, NOVICE)), "--level", "novice", "--dry-run"]) == 0
    assert not (tmp_path / "out").exists()
    assert "would write" in capsys.readouterr().out


def test_the_written_file_matches_the_existing_wordlist_shape(tmp_path, monkeypatch):
    """build_skeleton reads {meta, words}; a different shape would break it."""
    out = tmp_path / "out"
    out.mkdir()
    monkeypatch.setattr(it, "WORDLISTS", out)

    it.main([str(_write(tmp_path, NOVICE)), "--level", "novice"])

    data = json.loads((out / "tocfl_novice.json").read_text(encoding="utf-8"))
    assert set(data) == {"meta", "words"}
    assert data["meta"]["count"] == len(data["words"]) == 3
    assert {"traditional", "pinyin", "gloss"} <= set(data["words"][0])


def test_overlap_with_the_current_lists_is_reported(tmp_path, monkeypatch, capsys):
    """He needs to know how much of an import is genuinely new before generating."""
    monkeypatch.setattr(it, "WORDLISTS", tmp_path / "out")
    monkeypatch.setattr(it, "existing_words", lambda: {"水"})

    it.main([str(_write(tmp_path, NOVICE)), "--level", "novice", "--dry-run"])

    assert "1 already in the current lists, 2 new" in capsys.readouterr().out
