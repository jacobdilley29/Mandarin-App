"""AI conversation practice with Claude (spec §3.5).

Claude plays a Taiwan character in Traditional characters at the learner's level,
stays in character but gently recasts errors, and returns a structured turn:
the in-character reply, a teacher note (corrections + one nicer phrasing), and
any new words it used — for the post-conversation recap → SRS flow.

Requires ANTHROPIC_API_KEY; the app degrades gracefully without it (the Talk tab
is disabled and everything else works).
"""

from __future__ import annotations

import sqlite3

from .config import get_settings

MODEL = "claude-opus-4-8"

# Taiwan scenario roleplays, each with a canned opening line so a session can
# start instantly (and be previewed) before any API round-trip.
SCENARIOS = [
    {
        "id": "night_market",
        "emoji": "🌃",
        "title": "夜市小吃",
        "en": "Night-market vendor",
        "character": "a friendly night-market food stall vendor in Taipei",
        "opening": {"hanzi": "來喔！要吃點什麼？", "pinyin": "Lái o! Yào chī diǎn shénme?", "gloss": "Come on over! What would you like to eat?"},
    },
    {
        "id": "mrt",
        "emoji": "🚇",
        "title": "捷運遺失物",
        "en": "MRT lost-and-found",
        "character": "a helpful MRT station lost-and-found clerk",
        "opening": {"hanzi": "您好，請問有什麼需要幫忙的嗎？", "pinyin": "Nín hǎo, qǐngwèn yǒu shénme xūyào bāngmáng de ma?", "gloss": "Hello, how can I help you?"},
    },
    {
        "id": "landlord",
        "emoji": "🏠",
        "title": "租房子",
        "en": "Landlord",
        "character": "a landlord showing a room for rent in Taipei",
        "opening": {"hanzi": "你好，這間房間就是要出租的。", "pinyin": "Nǐ hǎo, zhè jiān fángjiān jiùshì yào chūzū de.", "gloss": "Hi, this is the room that's for rent."},
    },
    {
        "id": "coworker",
        "emoji": "💼",
        "title": "同事聊天",
        "en": "Coworker small talk",
        "character": "a friendly coworker chatting during a break",
        "opening": {"hanzi": "早安！今天天氣不錯耶。", "pinyin": "Zǎo'ān! Jīntiān tiānqì búcuò yē.", "gloss": "Morning! Nice weather today, huh."},
    },
    {
        "id": "new_friend",
        "emoji": "😊",
        "title": "認識新朋友",
        "en": "New friend",
        "character": "someone you just met at a language exchange in Taipei",
        "opening": {"hanzi": "嗨，很高興認識你！你是哪裡人？", "pinyin": "Hāi, hěn gāoxìng rènshì nǐ! Nǐ shì nǎlǐ rén?", "gloss": "Hi, nice to meet you! Where are you from?"},
    },
]

_SCENARIO_BY_ID = {s["id"]: s for s in SCENARIOS}


def scenario(scenario_id: str) -> dict | None:
    return _SCENARIO_BY_ID.get(scenario_id)


def available() -> bool:
    if not get_settings().anthropic_api_key:
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def known_words_summary(conn: sqlite3.Connection, limit: int = 120) -> str:
    """A compact summary of vocabulary the learner has been exposed to."""
    rows = conn.execute(
        """SELECT DISTINCT v.traditional
           FROM srs_cards c JOIN vocab v ON v.id = c.item_id
           WHERE c.item_type = 'vocab'
           LIMIT ?""",
        (limit,),
    ).fetchall()
    words = [r["traditional"] for r in rows]
    return "、".join(words) if words else "(the learner is a beginner; keep it very simple)"


def _system_prompt(sc: dict, known: str) -> str:
    return f"""\
You are roleplaying as {sc['character']}, speaking with a learner of Taiwanese \
Mandarin. This is a friendly practice conversation.

Rules — follow all of them:
- Write ONLY in Traditional Chinese characters (繁體字). Never simplified.
- Use natural TAIWAN Mandarin: Taiwan vocabulary (e.g. 捷運, 便當, 悠遊卡, 腳踏車, \
週末) and Taiwan sentence-final particles where natural (嗎/喔/耶/啦/呢).
- Keep your reply SHORT (1–2 sentences) and at the learner's level. The learner \
knows roughly these words: {known}. Prefer words they know; introduce at most one \
or two new words per turn and keep grammar simple.
- STAY IN CHARACTER. Do not break the roleplay in your `reply`.
- If the learner made mistakes, do NOT correct them inside the reply — instead \
put brief corrections in the teacher note and gently move the conversation on.

Return a structured turn with:
- reply: your in-character response (Traditional characters).
- reply_pinyin: Hanyu pinyin with tone marks for your reply, Taiwan readings.
- teacher_note.corrections: short, friendly notes on the learner's LAST message \
(grammar/word-choice/tone), in English. Empty list if it was fine.
- teacher_note.better: ONE more natural way the learner could have said their \
last message (Traditional characters), or null if theirs was already natural.
- new_words: any words in YOUR reply likely new to the learner, each with \
traditional, pinyin, and a short English gloss. Empty list if none."""


def reply(conn: sqlite3.Connection, scenario_id: str, history: list[dict], user_text: str) -> dict:
    """Generate one conversation turn. Raises RuntimeError if unavailable."""
    sc = scenario(scenario_id)
    if not sc:
        raise ValueError("unknown scenario")
    if not available():
        raise RuntimeError("conversation unavailable (no ANTHROPIC_API_KEY)")

    import anthropic
    from pydantic import BaseModel

    class TeacherNote(BaseModel):
        corrections: list[str]
        better: str | None

    class NewWord(BaseModel):
        hanzi: str
        pinyin: str
        gloss: str

    class Turn(BaseModel):
        reply: str
        reply_pinyin: str
        teacher_note: TeacherNote
        new_words: list[NewWord]

    messages = [
        {"role": m["role"], "content": m["content"]} for m in history
    ] + [{"role": "user", "content": user_text}]

    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=MODEL,
        max_tokens=1024,
        system=_system_prompt(sc, known_words_summary(conn)),
        messages=messages,
        output_format=Turn,
    )
    turn = response.parsed_output
    if turn is None:
        raise RuntimeError("model returned no parsable turn")
    return turn.model_dump()
