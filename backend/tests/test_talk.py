"""Tests for the Talk conversation flow (spec §3.5) with a stubbed Claude client."""

from __future__ import annotations

import sys
import types

from app import conversation
from app.routers import talk


def _stub_client(monkeypatch, turn: dict):
    monkeypatch.setattr(conversation, "available", lambda: True)

    class FakeParsed:
        def model_dump(self):
            return turn

    class FakeResp:
        parsed_output = FakeParsed()

    class FakeMessages:
        def parse(self, **kwargs):
            return FakeResp()

    class FakeClient:
        def __init__(self, *a, **k):
            self.messages = FakeMessages()

    fake = types.ModuleType("anthropic")
    fake.Anthropic = FakeClient
    monkeypatch.setitem(sys.modules, "anthropic", fake)


def test_scenarios_have_openings():
    for s in conversation.SCENARIOS:
        assert s["opening"]["hanzi"] and s["opening"]["pinyin"]


def test_reply_returns_structured_turn(conn, monkeypatch):
    _stub_client(
        monkeypatch,
        {
            "reply": "好喔，要不要加珍珠？",
            "reply_pinyin": "Hǎo o, yào bú yào jiā zhēnzhū?",
            "teacher_note": {"corrections": ["Use 一杯 not 一個 for drinks"], "better": "我要一杯珍奶"},
            "new_words": [{"hanzi": "珍珠", "pinyin": "zhēnzhū", "gloss": "tapioca pearls"}],
        },
    )
    turn = conversation.reply(conn, "night_market", [{"role": "assistant", "content": "來喔"}], "我要一個珍奶")
    assert turn["reply"].startswith("好喔")
    assert turn["teacher_note"]["better"] == "我要一杯珍奶"
    assert turn["new_words"][0]["hanzi"] == "珍珠"


def test_start_stores_canned_opening(conn):
    out = talk.start(talk.StartIn(scenario="night_market"), conn)
    assert out["opening"]["hanzi"]
    rows = conn.execute("SELECT role, content FROM talk_messages WHERE session_id = ?", (out["session_id"],)).fetchall()
    assert rows[0]["role"] == "assistant"


def test_message_persists_turn_and_recap_collects_new_words(conn, monkeypatch):
    _stub_client(
        monkeypatch,
        {
            "reply": "好喔！",
            "reply_pinyin": "Hǎo o!",
            "teacher_note": {"corrections": [], "better": None},
            "new_words": [{"hanzi": "珍珠", "pinyin": "zhēnzhū", "gloss": "tapioca pearls"}],
        },
    )
    session_id = talk.start(talk.StartIn(scenario="night_market"), conn)["session_id"]
    talk.message(talk.MessageIn(session_id=session_id, text="我要珍奶"), conn)

    recap = talk.recap(session_id, conn)
    hanzi = [w["hanzi"] for w in recap["words"]]
    assert "珍珠" in hanzi
    assert recap["words"][0]["in_deck"] is False

    added = talk.recap_add(talk.RecapAddIn(words=recap["words"]), conn)
    assert added["added"] == 1
    # The word now has a vocab row + an SRS card.
    row = conn.execute("SELECT id FROM vocab WHERE traditional = '珍珠'").fetchone()
    assert row is not None
    card = conn.execute(
        "SELECT 1 FROM srs_cards WHERE item_id = ? AND item_type='vocab'", (row["id"],)
    ).fetchone()
    assert card is not None


def test_message_without_key_raises(conn, monkeypatch):
    monkeypatch.setattr(conversation, "available", lambda: False)
    session_id = talk.start(talk.StartIn(scenario="mrt"), conn)["session_id"]
    try:
        talk.message(talk.MessageIn(session_id=session_id, text="你好"), conn)
        assert False, "expected HTTPException"
    except Exception as e:
        assert "503" in str(getattr(e, "status_code", "")) or "unavailable" in str(e).lower() or getattr(e, "status_code", None) == 503
