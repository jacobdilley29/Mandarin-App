"""The Listen tab's dictation drill, once it is built from tiles.

Typing Han on a phone means an IME between the learner and the answer, so the
drill hands them tiles instead. That moves work to the server: the tiles, their
readings and the decoys all have to come down with the item, and the two
sources the pool draws on — drill sentences and dialogue lines — do not have
the same shape. Sentences arrive pre-tokenised; a dialogue line is one string
and has to be segmented.
"""

from __future__ import annotations

import json

import pytest

from app import listen

from .conftest import attached_conn

SENTENCE = {"tokens": ["我", "要", "水"], "pinyin": "Wǒ yào shuǐ.", "gloss": "I want water"}
LINE = {"speaker": "A", "hanzi": "你好嗎？", "pinyin": "Nǐ hǎo ma?", "gloss": "how are you?"}

DECOY_VOCAB = (
    ("v_cha", "茶", "chá", "tea"),
    ("v_kafei", "咖啡", "kāfēi", "coffee"),
    ("v_mianbao", "麵包", "miànbāo", "bread"),
    ("v_shu", "書", "shū", "book"),
    ("v_bi", "筆", "bǐ", "pen"),
    ("v_zhuozi", "桌子", "zhuōzi", "table"),
)


def seed(conn, *, sentences=None, dialogue=None) -> None:
    conn.execute("INSERT INTO units (id, title, sort_order) VALUES ('u', 'U', 1)")
    conn.execute(
        "INSERT INTO lessons (id, unit_id, title, sort_order, sentences, dialogue) "
        "VALUES ('l', 'u', 'L', 1, ?, ?)",
        (json.dumps(sentences or []), json.dumps(dialogue or [])),
    )
    conn.executemany(
        "INSERT INTO vocab (id, traditional, pinyin, gloss, hsk_level) VALUES (?,?,?,?,1)",
        DECOY_VOCAB,
    )
    conn.commit()


@pytest.fixture
def db(tmp_path):
    c = attached_conn(tmp_path)
    yield c
    c.close()


def rack(item) -> list[str]:
    return [t["text"] for t in item["tiles"]]


def test_a_sentence_item_comes_with_tiles(db):
    seed(db, sentences=[SENTENCE])
    item = listen.dictation_item(db)
    assert item["answer"] == ["我", "要", "水"]
    assert set(item["tiles"][0]) == {"text", "pinyin", "zhuyin"}


def test_every_answer_token_is_on_the_rack(db):
    """Otherwise the exercise cannot be completed at all."""
    seed(db, sentences=[SENTENCE])
    item = listen.dictation_item(db)
    remaining = rack(item)
    for token in item["answer"]:
        assert token in remaining
        remaining.remove(token)


def test_the_rack_carries_decoys(db):
    seed(db, sentences=[SENTENCE])
    item = listen.dictation_item(db)
    assert len(item["tiles"]) > len(item["answer"])
    extras = rack(item)
    for token in item["answer"]:
        extras.remove(token)
    assert extras and not set(extras) & set(item["answer"])


def test_tiles_carry_readings_derived_from_the_sentence(db):
    seed(db, sentences=[SENTENCE])
    item = listen.dictation_item(db)
    by_text = {t["text"]: t for t in item["tiles"]}
    assert by_text["水"]["pinyin"] == "shuǐ"
    assert by_text["水"]["zhuyin"] == "ㄕㄨㄟˇ"


def test_a_dialogue_line_is_segmented_into_tiles(db):
    """A dialogue line is one string — no tokens — so it has to be segmented
    before it can be a tile rack. Its punctuation is not a tile."""
    seed(db, dialogue=[LINE])
    item = listen.dictation_item(db)
    assert item["hanzi"] == "你好嗎？"
    assert "？" not in rack(item)
    assert "".join(item["answer"]) == "你好嗎"


def test_readings_come_from_the_line_not_the_dictionary(db):
    """Segmentation may consult the dictionary; readings never do. The
    sentence's own pinyin is the source of truth — see app/zhuyin.py."""
    seed(db, dialogue=[{**LINE, "hanzi": "他和我", "pinyin": "tā hàn wǒ", "gloss": "he and I"}])
    item = listen.dictation_item(db)
    assert [t["pinyin"] for t in item["tiles"] if t["text"] == "和"] == ["hàn"]


def test_an_item_whose_reading_cannot_be_split_still_has_tiles(db):
    seed(db, sentences=[{**SENTENCE, "pinyin": "???"}])
    item = listen.dictation_item(db)
    assert item["answer"] == ["我", "要", "水"]
    assert rack(item)


def test_no_content_means_no_item(db):
    assert listen.dictation_item(db) is None
