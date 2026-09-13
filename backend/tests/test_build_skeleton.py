"""Building the curriculum skeleton (spec §3.1).

Two things worth pinning. Themed grouping is now the default — the offline
grouping produces units called "HSK 3 詞彙 7", which is a word-list position
wearing a title, and it was the default for months while the themed path went
unused. And themed grouping needs a key, which it must look for where the user
actually put it: `bin_claude` called `anthropic.Anthropic()` bare, so a key
entered in the app's Me tab themed nothing and failed on auth.
"""

from __future__ import annotations

from scripts import build_skeleton as bs


def test_without_a_key_it_stops_before_doing_any_work(monkeypatch, capsys):
    monkeypatch.setattr(bs, "resolve_api_key", lambda: None)

    assert bs.main(["--dry-run"]) == 1

    out = capsys.readouterr().out
    assert "needs an Anthropic key" in out
    assert "--theme offline" in out, "say how to proceed without one"


def test_offline_still_needs_no_key(monkeypatch, capsys):
    """The no-key path has to keep working, or a fresh checkout can't build."""
    monkeypatch.setattr(bs, "resolve_api_key", lambda: None)

    assert bs.main(["--theme", "offline", "--dry-run"]) == 0
    assert "would write" in capsys.readouterr().out


def test_the_default_is_themed_not_offline(monkeypatch, capsys):
    """The offline grouping was the default for months, and produces units
    called "HSK 3 詞彙 7" — a word-list position wearing a title. Asserted
    through behaviour, since main() builds its parser inline: with no key, the
    default path is the one that stops and asks for a key."""
    monkeypatch.setattr(bs, "resolve_api_key", lambda: None)

    assert bs.main(["--dry-run"]) == 1, "the default must be the themed path"
