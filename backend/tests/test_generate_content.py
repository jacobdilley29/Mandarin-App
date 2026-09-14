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
from app.validation import validate_curriculum
from scripts import generate_content as gc


class StubClient:
    """Stands in for anthropic.Anthropic, returning well-formed lesson content.

    Sentences are built only from the lesson's own vocabulary, so they validate.
    `stray` injects a character the learner has not met, to exercise the
    out-of-scope path.
    """

    def __init__(self, stray: str = "", output_tokens: int = 1200):
        self.stray = stray
        self.calls = 0
        self.output_tokens = output_tokens
        self.budgets: list[int] = []

    @property
    def messages(self):
        return self

    def stream(self, **kw):
        """The real client streams, so the stub is a context manager too.

        Non-streaming was how a long generation could fail on a request timeout
        for reasons unrelated to the content, so the shape matters enough to
        mirror here rather than stub around.
        """
        response = self.parse(**kw)
        client = self

        class _Stream:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def get_final_message(self):
                return response

        del client
        return _Stream()

    def parse(self, *, messages, max_tokens=None, **kw):
        self.calls += 1
        if max_tokens is not None:
            self.budgets.append(max_tokens)
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
                "contrast": "unlike X, this one …",
                "common_error": "learners drop the particle",
            }],
            "sentences": [{"tokens": [words[0]], "pinyin": "p", "gloss": "g", "cloze_index": 0}],
            "dialogue": [{"speaker": "A", "hanzi": words[0], "pinyin": "p", "gloss": "g"}],
            # Built from the lesson's own words, so it stays inside scope like
            # everything else the stub returns.
            "passage": {"title": "t", "hanzi": words[0] * 3, "gloss": "a short read"},
        }
        return types.SimpleNamespace(
            parsed_output=types.SimpleNamespace(model_dump=lambda: out),
            stop_reason="end_turn",
            usage=types.SimpleNamespace(output_tokens=self.output_tokens),
        )


@pytest.fixture(autouse=True)
def _reset_peak():
    """PEAK_TOKENS is per-run state; one test's peak must not leak into the next."""
    gc.PEAK_TOKENS = 0
    yield
    gc.PEAK_TOKENS = 0


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


def test_attempts_are_capped_and_the_cap_is_the_flag(sandbox):
    """The cap used to be one attempt, on the reasoning that a model ignoring an
    explicit ban would ignore it twice over.

    A real run disproved that: of five failures, three came back clean of the
    banned characters and tripped on a different word — converging, and stopped
    one step short. So the cap is --retries, and a lesson that never comes good
    costs exactly 1 + retries calls and not one more.
    """
    client = StubClient(stray="嚇")

    gc.main(["--unit", "u_draft", "--retries", "2"], client=client)

    assert client.calls == 3, "one generation plus two attempts"
    assert cs.load_unit("u_draft")["status"] == cs.STATUS_DRAFT


def test_no_retry_still_means_no_retry(sandbox):
    client = StubClient(stray="嚇")

    gc.main(["--unit", "u_draft", "--no-retry"], client=client)

    assert client.calls == 1


def test_a_successful_retry_replaces_the_cached_lesson(sandbox):
    """Otherwise the next run would reload the bad version from cache for free."""
    gc.main(["--unit", "u_draft"], client=StraysOnce())

    cached = json.loads((gc.GENERATED_DIR / "l_draft.json").read_text(encoding="utf-8"))
    assert "嚇" not in json.dumps(cached["_content"], ensure_ascii=False)
    # The ban itself is kept deliberately — see the accumulation tests below.
    assert cached["_rejected"] == ["嚇"]


def test_a_blocked_draft_is_still_selected_for_work(sandbox):
    """A unit held back by an out-of-scope sentence is complete but not done.

    Selection used to filter on completeness, so a unit whose lessons all had
    content but failed validation was skipped — the run reported "every unit in
    scope is already complete" about units the learner cannot see, and the retry
    that would have fixed them never got the chance.
    """
    unit = cs.load_unit("u_draft")
    assert completeness.evaluate_unit(unit).complete is False

    # Give it full content, as a generation run does, but leave it a draft —
    # exactly the state a validation failure leaves behind.
    gc.main(["--unit", "u_draft"], client=StubClient(stray="嚇"))
    blocked = cs.load_unit("u_draft")
    assert blocked["status"] == cs.STATUS_DRAFT
    assert completeness.evaluate_unit(blocked).complete, "it has all its content"

    args = types.SimpleNamespace(unit=None, level=None, all=False)
    selected = [u["id"] for u in gc._select_units(cs.load(), args)]

    assert "u_draft" in selected, "a blocked draft still needs work"
    assert "u_live" not in selected, "a finished unit is still left alone"


# ---------------------------------------------------------------------------
# The cache has to know what it was generated FOR
# ---------------------------------------------------------------------------
def test_changing_a_lesson_s_words_invalidates_its_cache(sandbox):
    """Lesson ids are positional, so re-theming reuses them with other words.

    A cache keyed on the id alone would hand back content written for a
    completely different word set, print "cached", and produce a lesson whose
    examples have nothing to do with its vocabulary — free, and looking like a
    successful run. That is the trap re-theming walks straight into.
    """
    gc.main(["--unit", "u_draft"], client=StubClient())

    unit = cs.load_unit("u_draft")
    unit["lessons"][0]["vocab"] = [
        {"id": "v_茶", "traditional": "茶", "pinyin": "chá", "gloss": "tea", "hsk_level": 1}
    ]
    unit["status"] = cs.STATUS_DRAFT
    cs.write_unit(unit)

    second = StubClient()
    gc.main(["--unit", "u_draft"], client=second)

    assert second.calls == 1, "different words must mean a regeneration, not a cache hit"


def test_the_same_words_still_hit_the_cache(sandbox):
    """The saving has to survive the fix, or every run pays full price.

    `--all` so the unit is reconsidered after the first run promotes it to live;
    without it this passes for the wrong reason — nothing is selected at all.
    """
    gc.main(["--unit", "u_draft"], client=StubClient())

    second = StubClient()
    gc.main(["--unit", "u_draft", "--all"], client=second)

    assert second.calls == 0


def test_a_cache_file_from_before_this_check_is_not_trusted(sandbox):
    """It carries no record of what it was for, so it cannot be verified.

    Costs one regeneration; the alternative is silently shipping mismatched
    content, which is the failure this whole check exists to prevent.
    """
    gc.main(["--unit", "u_draft"], client=StubClient())
    cached = gc.GENERATED_DIR / "l_draft.json"
    # Rewrite it in the old shape: the bare content, no fingerprint.
    payload = json.loads(cached.read_text(encoding="utf-8"))
    cached.write_text(json.dumps(payload["_content"], ensure_ascii=False), encoding="utf-8")

    second = StubClient()
    gc.main(["--unit", "u_draft", "--all"], client=second)

    assert second.calls == 1


def test_the_run_says_why_it_is_regenerating(sandbox, capsys):
    """"words changed" is the difference between a free run and a paid one."""
    gc.main(["--unit", "u_draft"], client=StubClient())
    unit = cs.load_unit("u_draft")
    unit["lessons"][0]["vocab"] = [{"id": "v_茶", "traditional": "茶", "gloss": "tea"}]
    unit["status"] = cs.STATUS_DRAFT
    cs.write_unit(unit)
    capsys.readouterr()

    gc.main(["--unit", "u_draft"], client=StubClient())

    assert "words changed" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Contrastive grammar and the reading passage
# ---------------------------------------------------------------------------
def test_a_generated_lesson_gets_a_reading_passage(sandbox):
    """Connected prose at the lesson's level — the thing drill sentences aren't."""
    gc.main(["--unit", "u_draft"], client=StubClient())

    passage = cs.load_unit("u_draft")["lessons"][0]["passage"]
    assert passage["hanzi"] and passage["gloss"]


def test_grammar_carries_what_it_contrasts_with(sandbox):
    """Zhong's framing: a pattern is learned by its boundaries, not its definition."""
    gc.main(["--unit", "u_draft"], client=StubClient())

    grammar = cs.load_unit("u_draft")["lessons"][0]["grammar"][0]
    assert grammar["contrast"]
    assert grammar["common_error"]


def test_an_out_of_scope_passage_is_caught_like_any_other_sentence(sandbox):
    """The passage is the longest text in a lesson and the easiest hiding place."""
    unit = cs.load_unit("u_draft")
    lesson = unit["lessons"][0]
    lesson["passage"] = {"title": "t", "hanzi": "他嚇到了", "gloss": "he got a fright"}
    cs.write_unit(unit)

    result = validate_curriculum(cs.load(), extra_known_chars=gc.placement_pool_chars())

    assert any("passage" in v.where and "嚇" in v.unknown for v in result.violations)


def test_a_missing_passage_does_not_hold_a_unit_back(sandbox):
    """Optional, so the units generated before this existed don't drop to draft."""
    report = completeness.evaluate_unit(cs.load_unit("u_live"))

    assert "passage_present" not in report.missing


def test_a_cache_entry_missing_a_new_field_is_regenerated(sandbox):
    """The other half of invalidation, and the half that is easy to miss.

    When lessons gained a reading passage, every cached lesson still had exactly
    the same words — so the word-set check passed and a regeneration run would
    have printed "• cached" for all of them and applied content with no passage
    in it. A paid-looking run that changes nothing, with no error anywhere.
    """
    gc.main(["--unit", "u_draft"], client=StubClient())
    cached = gc.GENERATED_DIR / "l_draft.json"
    payload = json.loads(cached.read_text(encoding="utf-8"))
    del payload["_content"]["passage"]  # a cache entry from before passages
    cached.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    second = StubClient()
    gc.main(["--unit", "u_draft", "--all"], client=second)

    assert second.calls == 1, "content missing a field the prompt asks for must be a miss"


def test_the_run_says_which_field_was_missing(sandbox, capsys):
    """A paid run must never be a mystery — it names what it is paying for."""
    gc.main(["--unit", "u_draft"], client=StubClient())
    cached = gc.GENERATED_DIR / "l_draft.json"
    payload = json.loads(cached.read_text(encoding="utf-8"))
    del payload["_content"]["passage"]
    cached.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    capsys.readouterr()

    gc.main(["--unit", "u_draft", "--all"], client=StubClient())

    assert "missing passage" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Truncation, and knowing about it before it costs 185 calls
# ---------------------------------------------------------------------------
class TruncatedClient(StubClient):
    """A response cut off at the token limit, which parses to nothing."""

    def parse(self, **kw):
        super().parse(**kw)
        return types.SimpleNamespace(
            parsed_output=None,
            stop_reason="max_tokens",
            usage=types.SimpleNamespace(output_tokens=gc.LESSON_BUDGET),
        )


def test_a_truncated_lesson_says_it_was_truncated(sandbox, capsys):
    """The error that sent two rounds of debugging at the wrong thing.

    parsed_output is None whether the model was cut off or returned nothing, and
    "model did not return valid content" reads as a key, model or schema
    problem — none of which are wrong. This is the exact failure that stalled
    the skeleton builder, in the script that makes 185 calls instead of 14.
    """
    gc.main(["--unit", "u_draft"], client=TruncatedClient())

    out = capsys.readouterr().out
    assert "cut off at the token limit" in out
    assert "Raise the max_tokens budget" in out


def test_a_truncated_lesson_is_not_cached(sandbox):
    """Caching a failure would make the next run free and still broken."""
    gc.main(["--unit", "u_draft"], client=TruncatedClient())
    assert not list((gc.GENERATED_DIR).glob("l_draft*.json")), "nothing to cache from a failure"


def test_the_run_reports_the_tokens_it_actually_needed(sandbox, capsys):
    """Every budget in this pipeline that was estimated rather than measured
    turned out wrong. This is the measurement."""
    gc.main(["--unit", "u_draft"], client=StubClient(output_tokens=1234))

    out = capsys.readouterr().out
    assert "peak tokens" in out
    assert "1234" in out and str(gc.LESSON_BUDGET) in out


def test_a_tight_budget_is_called_out(sandbox, capsys):
    """A lesson using most of its budget is the warning before the truncation."""
    gc.main(["--unit", "u_draft"], client=StubClient(output_tokens=gc.LESSON_BUDGET - 100))

    assert "raise LESSON_BUDGET" in capsys.readouterr().out


def test_a_comfortable_budget_is_not_nagged_about(sandbox, capsys):
    gc.main(["--unit", "u_draft"], client=StubClient(output_tokens=1000))

    assert "raise LESSON_BUDGET" not in capsys.readouterr().out


def test_the_lesson_budget_has_room_for_the_current_prompt(sandbox):
    """8000 was set when a lesson had no passage and no contrastive grammar."""
    client = StubClient()
    gc.main(["--unit", "u_draft"], client=client)

    assert client.budgets, "the budget must actually reach the API call"
    assert all(b >= 16000 for b in client.budgets)


# ---------------------------------------------------------------------------
# The retry has to converge, not go in circles
# ---------------------------------------------------------------------------
class StraysDifferently(StubClient):
    """Out of scope every time, on a different character each time.

    This is the shape the real failures took: told to avoid 較, it came back
    with 定; told to avoid 定, it came back with 較. Three of five failures in
    one run were converging like this and simply ran out of attempts.
    """

    def __init__(self, strays=("駱", "嚇", "鎮")):
        super().__init__()
        self.strays = list(strays)
        self.prompts: list[str] = []

    def parse(self, *, messages, **kw):
        self.prompts.append(messages[0]["content"])
        self.stray = self.strays[min(self.calls, len(self.strays) - 1)]
        return super().parse(messages=messages, **kw)


def test_every_attempt_is_told_everything_refused_so_far(sandbox):
    """The bug that let 南 and 隻 come back after being banned."""
    client = StraysDifferently()

    gc.main(["--unit", "u_draft", "--retries", "2"], client=client)

    first_retry, second_retry = client.prompts[1], client.prompts[2]
    assert "駱" in first_retry
    assert "駱" in second_retry, "the first ban must still be in force"
    assert "嚇" in second_retry, "and the second one added to it"


def test_the_ban_list_survives_into_the_next_run(sandbox):
    """Kept in the cache, so a lesson retried tomorrow starts from today."""
    gc.main(["--unit", "u_draft", "--retries", "1"], client=StraysDifferently())

    cached = json.loads((gc.GENERATED_DIR / "l_draft.json").read_text(encoding="utf-8"))
    assert "駱" in cached["_rejected"]

    later = StraysDifferently(strays=("鎮",))
    gc.main(["--unit", "u_draft", "--retries", "1"], client=later)
    assert "駱" in later.prompts[-1], "yesterday's ban is still a ban"


def test_attempts_stop_as_soon_as_the_lesson_is_clean(sandbox):
    """A second attempt on a lesson that already passed is money for nothing."""
    client = StraysOnce()

    gc.main(["--unit", "u_draft", "--retries", "3"], client=client)

    assert client.calls == 2, "one generation, one successful retry, then stop"
    assert cs.load_unit("u_draft")["status"] == cs.STATUS_LIVE


class WorseOnRetry(StubClient):
    """First attempt breaks scope once; the retry breaks it in two places.

    A retry is not automatically an improvement. One produced a sentence that
    was not grammatical at all, and caching it unconditionally made that the
    lesson's permanent version.
    """

    def parse(self, *, messages, **kw):
        self.stray = "駱" if self.calls == 0 else "駱嚇鎮"
        return super().parse(messages=messages, **kw)


def test_a_worse_retry_does_not_replace_the_better_draft(sandbox):
    gc.main(["--unit", "u_draft", "--retries", "1"], client=WorseOnRetry())

    lesson = cs.load_unit("u_draft")["lessons"][0]
    text = json.dumps(lesson, ensure_ascii=False)
    assert "嚇" not in text and "鎮" not in text, "the worse attempt was kept"
    cached = json.loads((gc.GENERATED_DIR / "l_draft.json").read_text(encoding="utf-8"))
    assert "嚇" not in json.dumps(cached["_content"], ensure_ascii=False)


def test_a_worse_retry_still_records_what_it_was_refused_for(sandbox):
    """Discarding the content does not mean discarding the lesson learned."""
    gc.main(["--unit", "u_draft", "--retries", "1"], client=WorseOnRetry())

    cached = json.loads((gc.GENERATED_DIR / "l_draft.json").read_text(encoding="utf-8"))
    assert {"嚇", "鎮"} <= set(cached["_rejected"])


def test_the_retry_note_bans_outright_and_asks_for_grammatical(sandbox):
    """The failures showed the model contorting sentences to dodge characters."""
    assert "BANNED" in gc.RETRY_NOTE
    assert "grammatical" in gc.RETRY_NOTE


def test_two_attempts_is_the_default(sandbox):
    """The default is the decision, so it needs pinning.

    One attempt was the old default and it lost units that were one step from
    passing. Dropping it back to one would look like a harmless tidy-up.
    """
    client = StubClient(stray="嚇")

    gc.main(["--unit", "u_draft"], client=client)

    assert client.calls == 3, "one generation plus two attempts, with no flag given"


# ---------------------------------------------------------------------------
# --refresh: the cache is wrong after a reorder, not stale
# ---------------------------------------------------------------------------
def test_refresh_regenerates_a_lesson_the_cache_would_have_served(sandbox):
    """A reorder changes what a lesson may use, not which words it teaches.

    So the fingerprint is unchanged and the cache hits, handing back content
    written for the lesson's old position — which is exactly the content the
    reorder was meant to replace. The HSK 1 units were generated behind fourteen
    HSK 2-4 units and came out with dialogues about taking the MRT; serving that
    from cache after moving them to the front would be the whole exercise wasted.
    """
    gc.main(["--unit", "u_draft"], client=StubClient())

    cached = StubClient()
    gc.main(["--unit", "u_draft", "--all"], client=cached)
    assert cached.calls == 0, "the cache hits when nothing has changed"

    refreshed = StubClient()
    gc.main(["--unit", "u_draft", "--all", "--refresh"], client=refreshed)
    assert refreshed.calls == 1


def test_refresh_says_that_is_why_it_is_paying(sandbox, capsys):
    gc.main(["--unit", "u_draft"], client=StubClient())
    capsys.readouterr()

    gc.main(["--unit", "u_draft", "--all", "--refresh"], client=StubClient())

    assert "refresh requested" in capsys.readouterr().out
