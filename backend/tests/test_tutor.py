"""Ask-a-question tutor (spec §3.7).

No API calls: a stub client stands in for Claude throughout, so the context
building, the thread storage and the degradation path are all tested on every
run, with no key and no spend.

What makes the tutor worth more than a generic chat window is the context §3.7
asks for — "the current unit/lesson, recently missed items" — so most of these
check that the context is real rather than nominal.
"""

from __future__ import annotations

import json
import types

import pytest

from app import srs, tutor

from .conftest import attached_conn


class StubClient:
    """Stands in for anthropic.Anthropic — captures what it was asked, answers well.

    `client.messages.parse(...)` is the shape the real SDK has, so `messages`
    returns the stub itself and the captured prompt lands in `sent`.
    """

    def __init__(self):
        self.system = None
        self.sent = None
        self.calls = 0

    @property
    def messages(self):
        return self

    def parse(self, *, system, messages, **kw):
        self.calls += 1
        self.system = system
        self.sent = messages
        out = {
            "answer": "才 means later than expected; 就 means sooner.",
            "examples": [{"hanzi": "他才來", "pinyin": "tā cái lái", "gloss": "He only just came."}],
            "taiwan_note": None,
            "related": ["g_le"],
        }
        return types.SimpleNamespace(
            parsed_output=types.SimpleNamespace(model_dump=lambda: out)
        )


@pytest.fixture
def conn(tmp_path):
    c = attached_conn(tmp_path)
    c.executemany(
        "INSERT INTO vocab (id, traditional, pinyin, gloss, hsk_level) VALUES (?,?,?,?,?)",
        [("v_cai", "才", "cái", "only then", 3), ("v_jiu", "就", "jiù", "then", 2)],
    )
    c.execute(
        """INSERT INTO grammar (id, title, pattern, explanation, examples)
           VALUES ('g_le', '了 — a completed action', 'V + 了', 'marks completion', '[]')"""
    )
    c.execute("INSERT INTO units (id, title, hsk_level, status) VALUES ('u1','便利商店',2,'live')")
    c.execute("INSERT INTO lessons (id, unit_id, title) VALUES ('l1','u1','Lesson 1')")
    c.commit()
    yield c
    c.close()


def _stub():
    s = StubClient()
    return s


# ---------------------------------------------------------------------------
# Context (spec §3.7)
# ---------------------------------------------------------------------------
def test_context_names_the_current_position(conn):
    conn.execute(
        """INSERT INTO lesson_progress (lesson_id, completed, completed_at)
           VALUES ('l1', 1, datetime('now'))"""
    )
    conn.commit()

    ctx = tutor._context(conn)
    assert "Lesson 1" in ctx and "便利商店" in ctx


def test_context_includes_recent_misses(conn):
    """§3.7 names "recently missed items" specifically."""
    conn.execute("INSERT INTO drill_errors (grammar_id) VALUES ('g_le')")
    cid = srs.ensure_new_card(conn, "vocab", "v_cai", "recognition")
    conn.execute("UPDATE srs_cards SET lapses = 3 WHERE id = ?", (cid,))
    conn.commit()

    ctx = tutor._context(conn)
    assert "了 — a completed action" in ctx
    assert "才" in ctx and "3x" in ctx


def test_a_fresh_learner_gets_a_usable_context(conn):
    """No progress yet must not produce a broken or empty prompt."""
    ctx = tutor._context(conn)
    assert "Lessons completed so far: 0" in ctx


@pytest.mark.parametrize(
    "focus, expected",
    [
        ({"type": "vocab", "id": "v_cai"}, "才"),
        ({"type": "grammar", "id": "g_le"}, "了 — a completed action"),
        ({"type": "sentence", "text": "我吃飽了"}, "我吃飽了"),
    ],
)
def test_focus_reaches_the_prompt(conn, focus, expected):
    """The item he was looking at is what makes 'why is 了 here' answerable."""
    assert expected in tutor._context(conn, focus)


def test_focus_is_looked_up_not_trusted(conn):
    """The client sends an id; the prompt describes the real curriculum row."""
    ctx = tutor._context(conn, {"type": "vocab", "id": "v_cai"})
    assert "only then" in ctx, "the gloss came from the database, not the request"


def test_an_unknown_focus_id_is_ignored_quietly(conn):
    ctx = tutor._context(conn, {"type": "vocab", "id": "v_nonexistent"})
    assert "v_nonexistent" not in ctx


# ---------------------------------------------------------------------------
# Asking
# ---------------------------------------------------------------------------
def test_asking_returns_a_structured_answer(conn):
    result = tutor.ask(conn, "What's the difference between 才 and 就?", client=_stub())

    assert result["answer"]
    assert result["examples"][0]["hanzi"] == "他才來"
    assert result["thread_id"]


def test_the_question_and_answer_are_persisted(conn):
    """Spec §7 counts tutor history as progress data — it has to be stored."""
    result = tutor.ask(conn, "Why 了 here?", client=_stub())

    messages = tutor.history(conn, result["thread_id"])
    assert [m["role"] for m in messages] == ["user", "assistant"]
    assert messages[0]["content"] == "Why 了 here?"


def test_history_lands_in_the_progress_database(conn):
    """Not content.db — it must survive a curriculum reseed and reach backups."""
    result = tutor.ask(conn, "Why 了 here?", client=_stub())

    row = conn.execute(
        "SELECT kind FROM progress.talk_sessions WHERE id = ?", (result["thread_id"],)
    ).fetchone()
    assert row["kind"] == "tutor"


def test_tutor_threads_are_distinguishable_from_roleplay(conn):
    tutor.ask(conn, "q", client=_stub())
    conn.execute("INSERT INTO talk_sessions (id, scenario, kind) VALUES ('r1','night_market','roleplay')")
    conn.commit()

    assert [t["id"] for t in tutor.threads(conn)] != []
    assert all(
        conn.execute("SELECT kind FROM talk_sessions WHERE id = ?", (t["id"],)).fetchone()["kind"] == "tutor"
        for t in tutor.threads(conn)
    )


def test_a_follow_up_carries_the_earlier_turns(conn):
    first = tutor.ask(conn, "What is 才?", client=_stub())
    stub = _stub()
    tutor.ask(conn, "And 就?", thread_id=first["thread_id"], client=stub)

    roles = [m["role"] for m in stub.sent]
    assert roles == ["user", "assistant", "user"], "the thread's history should be in the prompt"


def test_the_structured_answer_is_stored_for_replay(conn):
    result = tutor.ask(conn, "q", client=_stub())
    messages = tutor.history(conn, result["thread_id"])

    assert messages[1]["examples"][0]["hanzi"] == "他才來"


def test_focus_is_recorded_with_the_question(conn):
    result = tutor.ask(conn, "why?", focus={"type": "vocab", "id": "v_cai"}, client=_stub())

    assert tutor.history(conn, result["thread_id"])[0]["focus"]["id"] == "v_cai"


def test_the_system_prompt_carries_the_context(conn):
    stub = _stub()
    tutor.ask(conn, "q", focus={"type": "vocab", "id": "v_cai"}, client=stub)

    assert "currently studying" in stub.system
    assert "才" in stub.system


def test_the_prompt_demands_traditional_taiwan_examples(conn):
    """The whole app is Traditional/Taiwan; the tutor must not drift."""
    stub = _stub()
    tutor.ask(conn, "q", client=stub)

    assert "TRADITIONAL" in stub.system and "Taiwan" in stub.system


# ---------------------------------------------------------------------------
# Degradation
# ---------------------------------------------------------------------------
def test_no_key_raises_a_clear_runtime_error(conn, monkeypatch):
    monkeypatch.setattr(tutor.conversation, "effective_api_key", lambda c: None)

    with pytest.raises(RuntimeError, match="no Anthropic API key"):
        tutor.ask(conn, "q")


def test_an_empty_question_is_rejected_before_any_call(conn):
    stub = _stub()
    with pytest.raises(ValueError):
        tutor.ask(conn, "   ", client=stub)
    assert stub.calls == 0


def test_availability_matches_talk(conn, monkeypatch):
    """One key, one answer — the Me tab enables both or neither."""
    monkeypatch.setattr(tutor.conversation, "available", lambda c=None: True)
    assert tutor.available(conn) is True
