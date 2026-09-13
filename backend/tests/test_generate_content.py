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
                # The wire field name — apply_to_lesson maps it to `examples`.
                "example_sentences": [{"hanzi": words[0], "pinyin": "p", "gloss": "g"}],
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


class Exploding(StubClient):
    """A client where every call fails, as an outage or a rejected schema does."""

    def parse(self, **kw):
        raise RuntimeError("overloaded")


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


def test_a_level_filter_still_skips_finished_units(sandbox):
    """--level narrows the scope; it does not mean "regenerate everything here".

    It used to bypass the completeness check entirely, so asking for a level
    would rewrite the hand-authored live units at that level — paying the API
    to overwrite curated content with generated text.
    """
    live = cs.load_unit("u_live")
    client = StubClient()

    gc.main(["--level", str(live["hsk_level"])], client=client)

    assert cs.load_unit("u_live") == live, "the finished unit was left alone"


def test_naming_a_finished_unit_does_not_overwrite_it_either(sandbox):
    before = cs.load_unit("u_live")
    client = StubClient()

    assert gc.main(["--unit", "u_live"], client=client) == 0

    assert client.calls == 0
    assert cs.load_unit("u_live") == before


def test_all_is_the_one_way_to_regenerate_finished_units(sandbox):
    """The escape hatch stays — it just has to be asked for explicitly."""
    client = StubClient()

    gc.main(["--unit", "u_live", "--all"], client=client)

    assert client.calls >= 1


def test_a_unit_whose_lessons_all_fail_is_left_untouched(sandbox):
    """A network error must not rewrite content on disk.

    Every lesson failing used to still rewrite the unit file — and with it the
    unit's status. A generator outage could therefore demote hand-authored
    content to draft and pull it out of Learn.
    """
    before = cs.load_unit("u_draft")

    gc.main(["--unit", "u_draft"], client=Exploding())

    assert cs.load_unit("u_draft") == before


def test_a_live_unit_is_not_demoted_by_a_failed_run(sandbox):
    """The specific damage seen in the field: curated units turned into drafts."""
    before = cs.load_unit("u_live")

    gc.main(["--unit", "u_live", "--all"], client=Exploding())

    after = cs.load_unit("u_live")
    assert after == before
    assert cs.status_of(after) == cs.STATUS_LIVE


def test_the_generator_tells_the_model_about_the_placement_pool(sandbox):
    """The prompt's allowed list must include what the learner already knows.

    The pool is seeded as mastered before lesson one and never taught, so
    omitting it told the model 老師 and 朋友 were off-limits — and then the
    validator rejected the natural sentences it wrote anyway.
    """
    data = cs.load()
    first = data["units"][0]["lessons"][0]["id"]

    allowed = gc._allowed_words_upto(data, first)

    assert "老師" in allowed and "朋友" in allowed


def test_the_generator_and_the_loader_agree_on_what_is_in_scope(sandbox):
    """Two copies of "what counts as known" drifted apart once. Pin them together.

    The generator used to validate without the placement pool while
    load_content validated with it, so the generator discarded whole units of
    content that the loader would have accepted without complaint.
    """
    import scripts.load_content as lc

    assert gc.placement_pool_chars() == lc.placement_pool_chars()
    assert set("老師朋友學校") <= gc.placement_pool_chars()


class StraysOnce(StubClient):
    """Breaks scope on the first attempt, stays inside it on the retry."""

    def __init__(self):
        super().__init__(stray="嚇")
        self.prompts: list[str] = []

    def parse(self, *, messages, **kw):
        self.prompts.append(messages[0]["content"])
        if self.calls >= 1:
            self.stray = ""  # the retry behaves
        return super().parse(messages=messages, **kw)


def test_a_lesson_that_breaks_scope_is_retried_once(sandbox):
    """One stray character used to cost the whole lesson, and the call that made it."""
    client = StraysOnce()

    gc.main(["--unit", "u_draft"], client=client)

    assert client.calls == 2, "one generate, one retry"
    assert cs.load_unit("u_draft")["status"] == cs.STATUS_LIVE


def test_the_retry_says_which_characters_were_rejected(sandbox):
    """Re-asking without naming the problem is just paying for another guess."""
    client = StraysOnce()

    gc.main(["--unit", "u_draft"], client=client)

    assert "嚇" in client.prompts[1]
    assert "嚇" not in client.prompts[0], "the first attempt had no complaint to carry"


def test_no_retry_leaves_the_lesson_rejected(sandbox):
    client = StraysOnce()

    gc.main(["--unit", "u_draft", "--no-retry"], client=client)

    assert client.calls == 1
    assert cs.load_unit("u_draft")["status"] == cs.STATUS_DRAFT


def test_the_retry_is_capped_at_one_attempt(sandbox):
    """A model that can't stay in scope when told exactly what to avoid won't
    start on the third ask — it would just cost more."""
    client = StubClient(stray="嚇")

    gc.main(["--unit", "u_draft"], client=client)

    assert client.calls == 2
    assert cs.load_unit("u_draft")["status"] == cs.STATUS_DRAFT


def test_a_successful_retry_replaces_the_cached_lesson(sandbox):
    """Otherwise the next run would reload the bad version from cache for free."""
    gc.main(["--unit", "u_draft"], client=StraysOnce())

    cached = json.loads((gc.GENERATED_DIR / "l_draft.json").read_text(encoding="utf-8"))
    assert "嚇" not in json.dumps(cached, ensure_ascii=False)
