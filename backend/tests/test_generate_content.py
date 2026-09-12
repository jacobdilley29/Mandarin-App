"""The Claude generation pass and unit promotion (spec §5).

No API calls: a stub client stands in for Claude, so the promotion logic — the
part that decides whether generated content reaches the learner — is tested on
every run, by anyone, with no key and no spend.

The rule under test: a generated unit is promoted only when it BOTH validates
(every sentence stays inside the vocabulary taught so far) and is complete
(every required check passes). Failing either leaves it a draft.
"""

from __future__ import annotations

import json
import types

import pytest

from app import completeness, curriculum_source as cs
from scripts import generate_content as gc


class StubClient:
    """Stands in for anthropic.Anthropic, returning well-formed lesson content.

    Sentences are built only from the lesson's own vocabulary, so they validate.
    `stray` injects a character the learner has not met, to exercise the
    out-of-scope path.
    """

    def __init__(self, stray: str = ""):
        self.stray = stray
        self.calls = 0

    @property
    def messages(self):
        return self

    def parse(self, *, messages, **kw):
        self.calls += 1
        lines = [l.strip() for l in messages[0]["content"].splitlines() if l.strip().startswith("- [")]
        ids = [l.split("]")[0].lstrip("- [") for l in lines]
        words = [l.split("] ", 1)[1].split(" (")[0] for l in lines]

        out = {
            "vocab_examples": [
                {"vocab_id": i, "hanzi": w + self.stray, "pinyin": "p", "gloss": "g"}
                for i, w in zip(ids, words)
            ],
            "grammar": [{
                "title": "g", "pattern": "p", "explanation": "e",
                "examples": [{"hanzi": words[0], "pinyin": "p", "gloss": "g"}],
            }],
            "sentences": [{"tokens": [words[0]], "pinyin": "p", "gloss": "g", "cloze_index": 0}],
            "dialogue": [{"speaker": "A", "hanzi": words[0], "pinyin": "p", "gloss": "g"}],
        }
        return types.SimpleNamespace(
            parsed_output=types.SimpleNamespace(model_dump=lambda: out)
        )


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """A throwaway content directory holding one live unit and one draft."""
    monkeypatch.setattr(cs, "CONTENT_DIR", tmp_path)
    monkeypatch.setattr(cs, "MANIFEST_PATH", tmp_path / "curriculum.json")
    monkeypatch.setattr(cs, "UNITS_DIR", tmp_path / "units")
    monkeypatch.setattr(gc, "GENERATED_DIR", tmp_path / ".generated")

    live = {
        "id": "u_live", "title": "便利商店", "sort_order": 1, "hsk_level": 2,
        "lessons": [{
            "id": "l_live", "title": "L", "sort_order": 1,
            "vocab": [{"id": "v_shui", "traditional": "水", "pinyin": "shuǐ",
                       "gloss": "water", "hsk_level": 1,
                       "example": {"hanzi": "水", "pinyin": "p", "gloss": "g"}}],
            "grammar": [{"id": "g1", "title": "t", "pattern": "p", "explanation": "e",
                         "examples": []}],
            "sentences": [{"tokens": ["水"]}],
            "dialogue": [{"hanzi": "水"}],
        }],
    }
    draft = {
        "id": "u_draft", "title": "HSK 1 詞彙 1", "sort_order": 2, "hsk_level": 1,
        "generated": True, "status": "draft",
        "lessons": [{
            "id": "l_draft", "title": "L", "sort_order": 1,
            "vocab": [{"id": "v_cha", "traditional": "茶", "pinyin": "chá",
                       "gloss": "tea", "hsk_level": 1}],
            "grammar": [], "sentences": [], "dialogue": [],
        }],
    }
    cs.split({"meta": {"function_words": []}, "units": [live, draft]})
    return tmp_path


def test_a_completed_draft_is_promoted(sandbox):
    client = StubClient()

    assert gc.main(["--unit", "u_draft"], client=client) == 0

    assert cs.load_unit("u_draft")["status"] == cs.STATUS_LIVE
    assert client.calls == 1


def test_promotion_fills_in_every_missing_piece(sandbox):
    gc.main(["--unit", "u_draft"], client=StubClient())

    lesson = cs.load_unit("u_draft")["lessons"][0]
    assert lesson["grammar"] and lesson["sentences"] and lesson["dialogue"]
    assert lesson["vocab"][0]["example"]["hanzi"]
    assert completeness.evaluate_unit(cs.load_unit("u_draft")).complete


def test_out_of_scope_content_is_not_promoted(sandbox):
    """A sentence using a character the learner hasn't met keeps the unit back."""
    assert gc.main(["--unit", "u_draft"], client=StubClient(stray="駱")) == 0

    assert cs.load_unit("u_draft")["status"] == cs.STATUS_DRAFT


def test_incomplete_output_is_not_promoted(sandbox, monkeypatch):
    """Content that validates but leaves a required check failing stays draft."""
    def half(lesson, content):
        lesson["grammar"] = []          # grammar_seeded will fail
        lesson["sentences"] = content["sentences"]
        lesson["dialogue"] = content["dialogue"]

    monkeypatch.setattr(gc, "apply_to_lesson", half)
    gc.main(["--unit", "u_draft"], client=StubClient())

    assert cs.load_unit("u_draft")["status"] == cs.STATUS_DRAFT


def test_generated_grammar_gets_an_id(sandbox):
    """validate_curriculum and the DB loader both key on it; the model isn't asked for one."""
    gc.main(["--unit", "u_draft"], client=StubClient())

    grammar = cs.load_unit("u_draft")["lessons"][0]["grammar"][0]
    assert grammar["id"]


def test_results_are_cached_so_a_rerun_costs_nothing(sandbox):
    gc.main(["--unit", "u_draft"], client=StubClient())

    second = StubClient()
    gc.main(["--unit", "u_draft"], client=second)
    assert second.calls == 0, "a cached lesson must not be regenerated"


def test_a_failing_lesson_does_not_sink_the_run(sandbox):
    class Exploding(StubClient):
        def parse(self, **kw):
            raise RuntimeError("overloaded")

    assert gc.main(["--unit", "u_draft"], client=Exploding()) == 0
    assert cs.load_unit("u_draft")["status"] == cs.STATUS_DRAFT


def test_default_target_is_drafts_only(sandbox):
    """A finished unit is never regenerated by accident."""
    client = StubClient()
    gc.main([], client=client)

    assert client.calls == 1, "only the draft should have been generated"
    assert cs.load_unit("u_live")["lessons"][0]["vocab"][0]["example"]["hanzi"] == "水"


def test_dry_run_calls_nothing_and_writes_nothing(sandbox):
    before = cs.load_unit("u_draft")
    client = StubClient()

    assert gc.main(["--dry-run"], client=client) == 0
    assert client.calls == 0
    assert cs.load_unit("u_draft") == before


def test_vocab_examples_match_by_id_not_position(sandbox):
    lesson = {"id": "l", "vocab": [{"id": "a"}, {"id": "b"}]}
    gc.apply_to_lesson(lesson, {
        "vocab_examples": [
            {"vocab_id": "b", "hanzi": "B", "pinyin": "p", "gloss": "g"},
            {"vocab_id": "a", "hanzi": "A", "pinyin": "p", "gloss": "g"},
        ],
        "grammar": [], "sentences": [], "dialogue": [],
    })

    assert lesson["vocab"][0]["example"]["hanzi"] == "A"
    assert lesson["vocab"][1]["example"]["hanzi"] == "B"


def test_vocab_examples_fall_back_to_position_when_ids_do_not_match(sandbox):
    """A renamed id shouldn't cost the unit its examples and strand it in draft."""
    lesson = {"id": "l", "vocab": [{"id": "a"}, {"id": "b"}]}
    gc.apply_to_lesson(lesson, {
        "vocab_examples": [
            {"vocab_id": "wrong1", "hanzi": "A", "pinyin": "p", "gloss": "g"},
            {"vocab_id": "wrong2", "hanzi": "B", "pinyin": "p", "gloss": "g"},
        ],
        "grammar": [], "sentences": [], "dialogue": [],
    })

    assert lesson["vocab"][0]["example"]["hanzi"] == "A"
    assert lesson["vocab"][1]["example"]["hanzi"] == "B"


# ---------------------------------------------------------------------------
# Where the API key comes from
# ---------------------------------------------------------------------------
def test_a_key_entered_in_the_app_is_found(tmp_path, monkeypatch):
    """The Me tab stores it in progress.db. That must be enough on its own.

    Entering a key in the app and finding generation still says "not set" is a
    dead end with no visible cause, so all three sources are checked.
    """
    from app import config, conversation, db
    from scripts import generate_content as g

    settings = config.Settings(data_dir=tmp_path, anthropic_api_key=None)
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    monkeypatch.setattr(db, "get_settings", lambda: settings)
    monkeypatch.setattr(conversation, "get_settings", lambda: settings)
    db.init_db()
    conn = db.connect()
    conn.execute("UPDATE settings SET anthropic_api_key = 'sk-in-app'")
    conn.commit()
    conn.close()

    assert g.resolve_api_key() == "sk-in-app"


def test_the_env_key_is_used_when_the_app_has_none(tmp_path, monkeypatch):
    from app import config, conversation, db
    from scripts import generate_content as g

    settings = config.Settings(data_dir=tmp_path, anthropic_api_key="sk-in-env")
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    monkeypatch.setattr(db, "get_settings", lambda: settings)
    monkeypatch.setattr(conversation, "get_settings", lambda: settings)

    assert g.resolve_api_key() == "sk-in-env"


def test_the_in_app_key_wins_over_the_environment(tmp_path, monkeypatch):
    """Matches how the Talk tab resolves it — one precedence, not two."""
    from app import config, conversation, db
    from scripts import generate_content as g

    settings = config.Settings(data_dir=tmp_path, anthropic_api_key="sk-in-env")
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    monkeypatch.setattr(db, "get_settings", lambda: settings)
    monkeypatch.setattr(conversation, "get_settings", lambda: settings)
    db.init_db()
    conn = db.connect()
    conn.execute("UPDATE settings SET anthropic_api_key = 'sk-in-app'")
    conn.commit()
    conn.close()

    assert g.resolve_api_key() == "sk-in-app"


def test_no_key_anywhere_resolves_to_none(tmp_path, monkeypatch):
    from app import config, conversation, db
    from scripts import generate_content as g

    settings = config.Settings(data_dir=tmp_path, anthropic_api_key=None)
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    monkeypatch.setattr(db, "get_settings", lambda: settings)
    monkeypatch.setattr(conversation, "get_settings", lambda: settings)

    assert g.resolve_api_key() is None
