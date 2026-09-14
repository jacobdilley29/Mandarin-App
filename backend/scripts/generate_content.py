#!/usr/bin/env python3
"""Generate lesson content with the Claude API (spec §5).

For each lesson in a *skeleton* curriculum (units + lessons + the target
vocab/grammar ids), this asks Claude to write the Taiwan-flavoured example
sentences, drill sentences, and dialogue — constrained to the vocabulary
available at that point in the curriculum — then validates the result and
writes it into content/curriculum.json.

Design goals from the spec:
  - Batched + resumable: each lesson's generation is cached under
    content/.generated/<lesson_id>.json; re-running skips completed lessons.
  - Output committed as JSON so regeneration is optional (the app ships with
    hand-authored content and never requires this script or an API key).
  - Every generated sentence is validated against the allowed-character set;
    violations are reported and the lesson is left for regeneration.

Usage:
    ANTHROPIC_API_KEY=... python -m scripts.generate_content --skeleton skeleton.json
    python -m scripts.generate_content --lesson l_conv_1   # one lesson

This is an authoring tool. It is NOT needed to run the app.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import completeness, curriculum_source, llm  # noqa: E402
from app.config import REPO_ROOT
from app.llm import MODEL  # noqa: E402
from app.validation import (  # noqa: E402
    han_chars,
    placement_pool_chars,
    placement_pool_words,
    register_slips,
    validate_curriculum,
)


GENERATED_DIR = REPO_ROOT / "content" / ".generated"

SYSTEM_PROMPT = """\
You are a Taiwanese Mandarin curriculum author. Write natural, everyday
Taiwan-register Mandarin for a HelloChinese-style learning app.

Hard rules:
- Traditional characters only. Taiwan usage and vocabulary (e.g. 腳踏車 not 自行車,
  捷運, 便當, 悠遊卡, 週末). Taiwan register particles where natural (喔/耶/啦).
- Greetings the Taiwan way: 早安 (never 早上好), 晚安 (never 晚上好), 午安. Likewise
  馬鈴薯 not 土豆, 影片 not 視頻, 訊息 not 信息, 冷氣 not 空調, 品質 not 質量,
  泡麵 not 方便麵, 軟體 not 軟件. A Mainland word in a Taiwan lesson teaches the
  learner something this app exists to get right.
- Every sentence you write may ONLY use characters from the ALLOWED set you are
  given (the learner's known vocabulary so far, plus this lesson's new words and
  the common function words). Do not introduce any character outside that set.
- Pinyin uses tone marks (diacritics), Taiwan readings where they differ.
- Keep sentences short and level-appropriate for HSK 2–3.
"""


def _lesson_prompt(lesson: dict, allowed_words: list[str]) -> str:
    vocab_lines = "\n".join(
        f"  - [{v['id']}] {v['traditional']} ({v['pinyin']}): {v['gloss']}"
        for v in lesson["vocab"]
    )
    return f"""\
Lesson: {lesson['title']}

New vocabulary this lesson:
{vocab_lines}

ALLOWED characters come from these words (plus the standard function-word list):
{' '.join(sorted(set(''.join(allowed_words))))}

Write, as JSON matching the provided schema:
- one example sentence for EVERY new vocabulary word above, in `vocab_examples`,
  keyed by the word's id — a short, natural Taiwan-register sentence that shows
  the word in use. Every word must get one; the lesson is not usable without them.
- one grammar point that uses this lesson's vocab, with 3 example sentences
  in `example_sentences`. Also give `contrast` — the pattern it is most easily
  confused with and what decides between them — and `common_error`, the mistake
  learners actually make with it, in plain English. Use null for either only
  when there is genuinely nothing to say; a manufactured contrast is worse than
  none,
- 5 short drill sentences, each split into word tokens, each with a cloze_index
  pointing at a good word to blank out (prefer a new-vocab word),
- a 4–6 line dialogue set in a Taiwan daily-life scene using this vocab,
- a `passage`: 60–120 characters of connected prose set in Taiwan, using this
  lesson's vocabulary, with a short title and an English translation. Not a list
  of sentences — a small piece of writing someone would actually read.
Every Chinese string must stay within the ALLOWED characters.
"""


# --- Structured-output schema (Pydantic) ---
def _make_models():
    from pydantic import BaseModel

    class Example(BaseModel):
        hanzi: str
        pinyin: str
        gloss: str

    class Grammar(BaseModel):
        title: str
        pattern: str
        explanation: str
        # A pattern is learned by its boundaries. What it is confused with, and
        # the mistake learners actually make, are worth more than a longer
        # definition — and are what a reference grammar gives you that a
        # vocabulary list does not.
        contrast: str | None
        common_error: str | None
        # NOT `examples`. That is a reserved JSON Schema keyword, and pydantic
        # emits a $ref for such a field while dropping its $defs entry, so the
        # schema the SDK sends references a definition that isn't there and the
        # API rejects the request with a 400. Mapped back to `examples` in
        # apply_to_lesson, so the stored content keeps its usual shape.
        # See tests/test_output_schemas.py.
        example_sentences: list[Example]

    class Sentence(BaseModel):
        tokens: list[str]
        pinyin: str
        gloss: str
        cloze_index: int

    class DialogueLine(BaseModel):
        speaker: str
        hanzi: str
        pinyin: str
        gloss: str

    class VocabExample(BaseModel):
        vocab_id: str
        hanzi: str
        pinyin: str
        gloss: str

    class Passage(BaseModel):
        title: str
        hanzi: str
        gloss: str

    class LessonContent(BaseModel):
        vocab_examples: list[VocabExample]
        grammar: list[Grammar]
        sentences: list[Sentence]
        dialogue: list[DialogueLine]
        # Connected prose at exactly this lesson's level, so the learner reads
        # rather than decodes. Generated in the same call as everything else,
        # so it costs nothing on top.
        passage: Passage

    return LessonContent


RETRY_NOTE = """\
Earlier attempts at this lesson used characters the learner has not met yet. \
These are now BANNED outright — not one of them may appear anywhere in your \
output, in any word: {chars}

Rewrite the whole lesson. Keep the same vocabulary and the same teaching intent, \
but express every sentence using ONLY the allowed characters above.

Two things matter more than cleverness here. Every sentence must be **natural \
and grammatical** — a contorted sentence written to dodge a character is worse \
than a plain one, and much worse than a wrong one. And if a sentence needs a \
word you may not use, write about something else instead of forcing it: a \
simpler lesson is worth far more than one that gets thrown away."""


# max_tokens for one lesson. Was 8000, set when a lesson was a grammar point,
# some drill sentences and a dialogue. It now also asks for `contrast`,
# `common_error` and a 60-120 character passage with a title and translation —
# so the output grew and the budget did not, and 8000 has never actually been
# run against this prompt.
#
# No chunking, unlike the skeleton builder: one lesson is already a bounded unit
# of work (5-8 words), where a level is up to 590. It just needs headroom.
# PEAK_TOKENS reports what a run really used, so this is a measurement next time
# rather than another estimate.
LESSON_BUDGET = 16000

# Highest output-token count any lesson in this run needed.
PEAK_TOKENS = 0


def generate_lesson(
    client, lesson: dict, allowed_words: list[str], rejected: list[str] | None = None
) -> dict:
    """One lesson's content. `rejected` re-asks, naming what went out of scope."""
    global PEAK_TOKENS

    LessonContent = _make_models()
    prompt = _lesson_prompt(lesson, allowed_words)
    if rejected:
        prompt += "\n\n" + RETRY_NOTE.format(chars=" ".join(sorted(set(rejected))))
    # Streamed: a full lesson is a long generation, and a non-streaming request
    # of this size can exceed the request timeout for reasons that have nothing
    # to do with the content.
    with client.messages.stream(
        model=MODEL,
        max_tokens=LESSON_BUDGET,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        output_format=LessonContent,
    ) as stream:
        response = stream.get_final_message()

    used = getattr(getattr(response, "usage", None), "output_tokens", None)
    if isinstance(used, int):
        PEAK_TOKENS = max(PEAK_TOKENS, used)
    return llm.parsed_or_raise(response, lesson["id"]).model_dump()


def _allowed_words_upto(skeleton: dict, lesson_id: str) -> list[str]:
    """Cumulative vocabulary available up to and including a lesson.

    **This is where teaching order and generation scope are the same thing.**
    A lesson may use anything taught before it, and "before" means `sort_order`.
    So settle the curriculum's order *before* generating: content written at
    position 15 assumes everything in positions 1-14, and moving it to position 1
    later does not make it beginner material — it makes it broken. The generated
    HSK 1 units were written behind fourteen HSK 2-4 units and came out with
    dialogues about taking the MRT. See scripts/reorder_units.py.

    Starts from the placement pool: those words are seeded as already-mastered
    before lesson one and never taught, so they are in scope throughout. Leaving
    them out told the model it could not use 老師, 學校 or 朋友 — which is not
    true of the learner, and made natural Taiwan sentences fail validation.
    """
    words: list[str] = list(placement_pool_words())
    units = sorted(skeleton["units"], key=lambda u: u.get("sort_order", 0))
    for unit in units:
        for lesson in sorted(unit["lessons"], key=lambda l: l.get("sort_order", 0)):
            words.extend(v["traditional"] for v in lesson.get("vocab", []))
            if lesson["id"] == lesson_id:
                return words
    return words


def apply_to_lesson(lesson: dict, content: dict) -> None:
    """Write generated content back onto a lesson, in place.

    Vocab examples are matched by id and fall back to positional order, because
    a model that renames an id shouldn't cost the whole lesson its examples —
    without them the unit can never satisfy `examples_present` and would sit in
    draft forever with no obvious reason why.
    """
    # Grammar points need a stable id: both validate_curriculum and the DB
    # loader key on it, and the model isn't asked to invent one. Deriving it
    # from the lesson id keeps it stable across regenerations of that lesson.
    grammar = []
    for i, g in enumerate(content.get("grammar") or [], start=1):
        g = dict(g)
        # The wire field is example_sentences (see _make_models); everything
        # downstream — the DB loader, the validator, the app — reads `examples`.
        if "example_sentences" in g:
            g["examples"] = g.pop("example_sentences")
        g.setdefault("id", f"g_{lesson['id'].removeprefix('l_')}_{i}")
        g.setdefault("hsk_level", (lesson.get("vocab") or [{}])[0].get("hsk_level"))
        grammar.append(g)

    lesson["grammar"] = grammar
    lesson["sentences"] = content.get("sentences") or []
    lesson["dialogue"] = content.get("dialogue") or []
    if passage := content.get("passage"):
        lesson["passage"] = passage

    examples = content.get("vocab_examples") or []
    by_id = {e["vocab_id"]: e for e in examples if e.get("vocab_id")}
    for i, v in enumerate(lesson.get("vocab") or []):
        ex = by_id.get(v["id"]) or (examples[i] if i < len(examples) else None)
        if ex:
            v["example"] = {"hanzi": ex["hanzi"], "pinyin": ex["pinyin"], "gloss": ex["gloss"]}


def resolve_api_key() -> str | None:
    """The Anthropic key from wherever the user actually put it.

    Three places, and all three have to work, because each is the obvious one
    from a different starting point: the Me tab in the app (stored in
    progress.db — no file editing, and the only option if you only ever touch
    the UI), ANTHROPIC_API_KEY in .env, or an export in the shell.

    app.conversation.effective_api_key already implements exactly this
    precedence for the Talk tab, so it is reused rather than reimplemented —
    otherwise a key entered in the app enables Talk but mysteriously does not
    work here, which is precisely the trap this replaced.
    """
    from app import conversation, db

    try:
        conn = db.connect()
    except Exception:
        # No database yet (fresh checkout) — .env and the environment still work.
        return conversation.effective_api_key(None)
    try:
        return conversation.effective_api_key(conn)
    finally:
        conn.close()


def make_client(api_key: str | None = None):
    import anthropic

    return anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()


def _select_units(data: dict, args) -> list[dict]:
    """Which units to generate: narrow by id/level, then drop the finished ones.

    --unit and --level narrow *what is considered*; status still decides what is
    generated, unless --all says otherwise. They used to return their match
    directly and skip that filter, so `--level 3` meant "every HSK 3 unit" —
    including the hand-authored, hand-corrected live ones, which it would then
    pay to overwrite with generated text. Only --all does that now, which is
    what its help has always said.

    The filter is *status*, not completeness. A unit blocked by an out-of-scope
    sentence has all its content — it is "complete" — but it is still a draft
    and still needs work. Filtering on completeness skipped exactly those units,
    reporting "every unit in scope is already complete" about units the learner
    cannot see, and denying them the retry that would fix them.
    """
    units = sorted(data.get("units", []), key=lambda u: u.get("sort_order", 0))
    narrowed = bool(args.unit or args.level)
    if args.unit:
        units = [u for u in units if u["id"] in set(args.unit)]
    if args.level:
        units = [u for u in units if u.get("hsk_level") in set(args.level)]
    # --refresh on a named unit or level means "do these again", so it reaches
    # live units the way --all does. Without this it was unusable for the job it
    # exists for: after a reorder the units needing regeneration are precisely
    # the ones already marked live, so selection skipped every one of them and
    # the run reported "every unit in scope is already complete".
    if args.all or (args.refresh and narrowed):
        return units
    return [
        u for u in units
        if curriculum_source.status_of(u) != curriculum_source.STATUS_LIVE
    ]


# What a cached lesson is expected to contain. Bump this whenever the prompt
# starts asking for something a cached lesson would not have — it is the other
# half of cache invalidation, and the half that is easy to forget.
#
# The word set alone is not enough. When lessons gained a reading passage and
# contrastive grammar, every cached lesson still had exactly the same words, so
# a regeneration run would have reported "• cached" for all 185 of them and
# applied content with no passage in it: a paid-looking run that changed nothing,
# with no error anywhere. Naming the fields the content must carry means a
# prompt that grows a field invalidates the cache by itself.
CONTENT_FIELDS = ("vocab_examples", "grammar", "sentences", "dialogue", "passage")


def _lesson_fingerprint(lesson: dict) -> list[str]:
    """The vocabulary ids this lesson teaches — what its content was written for."""
    return [v["id"] for v in (lesson.get("vocab") or []) if v.get("id")]


def _has_current_shape(content: dict) -> bool:
    """Whether cached content carries everything the prompt now asks for."""
    return isinstance(content, dict) and all(f in content for f in CONTENT_FIELDS)


def read_cache(path: Path, lesson: dict) -> dict | None:
    """Cached content for this lesson, or None when it cannot be trusted.

    Lesson ids are positional — l_hsk2_01_1 is "the first lesson of the first
    HSK 2 unit", whatever words that unit currently holds. Re-theming regroups
    the words and keeps the ids, so a cache keyed on the id alone would hand back
    content written for an entirely different word set, print "cached", and
    produce a lesson whose examples have nothing to do with its vocabulary — for
    free, and looking like success. So the cache records what it was generated
    for, and a changed word set is a miss.

    The same applies to the *shape* of the content: a cache entry written before
    the prompt asked for a reading passage has the right words and the wrong
    fields, and trusting it would quietly produce a lesson missing everything
    the run was for. See CONTENT_FIELDS.

    A cache file from before this existed cannot be checked, so it is not
    trusted. That costs a regeneration once, which is the safe direction.
    """
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "_content" not in payload:
        return None
    if payload.get("_for_vocab") != _lesson_fingerprint(lesson):
        return None
    if not _has_current_shape(payload["_content"]):
        return None
    return payload["_content"]


def _miss_reason(path: Path, lesson: dict) -> str:
    """Why this lesson is about to cost a call — so a paid run is never a mystery."""
    if not path.is_file():
        return "generating"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "cache unreadable"
    if not isinstance(payload, dict) or "_content" not in payload:
        return "cache from an older format"
    if payload.get("_for_vocab") != _lesson_fingerprint(lesson):
        return "words changed"
    missing = [f for f in CONTENT_FIELDS if f not in payload["_content"]]
    if missing:
        return f"missing {', '.join(missing)}"
    return "regenerating"


def read_rejected(path: Path) -> set[str]:
    """Every character this lesson has ever been refused for.

    Retries used to see only the *current* run's violations, so a lesson could
    be told to avoid 較, come back using 定, be told to avoid 定, and come back
    using 較 again. Twice in one real run a retry re-used a character it had
    just been banned from (南, 隻) — because by then nothing was still saying so.

    Kept in the cache rather than in memory so the bans survive the run, and a
    lesson retried tomorrow starts from everything learned about it today.
    """
    if not path.is_file():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    if not isinstance(payload, dict):
        return set()
    return set(payload.get("_rejected") or [])


def _remember_rejected(path: Path, rejected: set[str]) -> None:
    """Record a ban without touching the cached content.

    A retry that came back no better must not become the cached version, but
    what it was refused for is still worth knowing — the next attempt should
    start from every character tried so far, not repeat one.
    """
    if not path.is_file():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(payload, dict):
        return
    payload["_rejected"] = sorted(set(payload.get("_rejected") or []) | set(rejected))
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_cache(
    path: Path, lesson: dict, content: dict, rejected: set[str] | None = None
) -> None:
    """Cache a lesson's content, keeping its accumulated ban list.

    `rejected` accumulates: what a lesson was refused for does not stop being
    true because a later attempt avoided it.
    """
    banned = read_rejected(path) | set(rejected or ())
    path.write_text(
        json.dumps(
            {
                "_for_vocab": _lesson_fingerprint(lesson),
                "_rejected": sorted(banned),
                "_content": content,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _violations_for(data: dict, by_id: dict, unit: dict) -> list:
    """This unit's out-of-scope sentences, judged as the content loader judges them.

    `where` reads like "l_conv_1 sentence 3", so the first token is the lesson
    id — only this unit's violations decide this unit's fate.
    """
    result = validate_curriculum(
        {"meta": data.get("meta", {}), "units": list(by_id.values())},
        # The same known-set load_content uses. Without it the generator was
        # stricter than the loader and discarded content `make load-content`
        # would have accepted — 17 of 23 units in one run.
        extra_known_chars=placement_pool_chars(),
    )
    lesson_ids = {l["id"] for l in (unit.get("lessons") or [])}
    return [v for v in result.violations if v.where.split()[0] in lesson_ids]


def _by_lesson(violations: list) -> dict[str, set[str]]:
    """Out-of-scope characters, grouped by the lesson that used them."""
    out: dict[str, set[str]] = {}
    for v in violations:
        out.setdefault(v.where.split()[0], set()).update(v.unknown)
    return out


# Where a lesson keeps its generated content, for restoring the best attempt.
_CONTENT_KEYS = ("vocab", "grammar", "sentences", "dialogue", "passage")


def _retry_lessons(
    client, data: dict, by_id: dict, unit: dict, violations: list, attempts: int
) -> int:
    """Re-ask the lessons that broke scope, until they stop breaking it.

    Three things this has to get right, each learned from a run that got it
    wrong.

    **The ban list accumulates.** Every attempt is told every character this
    lesson has ever been refused for, not only the latest batch. Without that it
    cycles: told to avoid a character it returns another, is told to avoid that
    one, and comes back to the first. Twice in one real run a retry re-used a
    character it had just been banned from, because by then nothing was still
    saying so.

    **More than one attempt.** This was capped at one, on the reasoning that a
    model which ignores an explicit ban will ignore it twice over. The evidence
    says otherwise: of five failures in that run, three came back clean of the
    banned characters and tripped on a different word instead. That is
    converging, and it was being stopped one step short.

    **The best attempt wins, not the last.** A retry can be worse than what it
    replaced, and caching it unconditionally made the worse version permanent.
    Each attempt is scored by how much of the lesson is still out of scope, and
    only an improvement is kept.
    """
    wanted = _by_lesson(violations)
    redone = 0

    for lesson in unit.get("lessons") or []:
        if lesson["id"] not in wanted:
            continue
        cache = GENERATED_DIR / f"{lesson['id']}.json"
        banned = read_rejected(cache) | wanted[lesson["id"]]
        best = {k: copy.deepcopy(lesson[k]) for k in _CONTENT_KEYS if k in lesson}
        best_score = len(wanted[lesson["id"]])

        for attempt in range(1, attempts + 1):
            label = f"attempt {attempt}/{attempts}" if attempts > 1 else "retrying"
            print(f"  ↻ {lesson['id']}: {label} — avoiding: {' '.join(sorted(banned))}")
            try:
                content = generate_lesson(
                    client, lesson, _allowed_words_upto(data, lesson["id"]),
                    rejected=sorted(banned),
                )
            except Exception as exc:  # noqa: BLE001 — a failed attempt is not fatal
                print(f"  ✗ {lesson['id']}: {exc}")
                break

            apply_to_lesson(lesson, content)
            still = _by_lesson(_violations_for(data, by_id, unit)).get(lesson["id"], set())
            banned |= still

            if len(still) < best_score:
                best = {k: copy.deepcopy(lesson[k]) for k in _CONTENT_KEYS if k in lesson}
                best_score = len(still)
                write_cache(cache, lesson, content, rejected=banned)
                redone += 1
                if not still:
                    print(f"  ✓ {lesson['id']}: back in scope")
                    break
            else:
                # Not an improvement, so it must not become the cached version.
                # The ban it earned is still worth keeping for the next attempt.
                print(f"  · {lesson['id']}: no better — keeping the earlier draft")
                _remember_rejected(cache, banned)

        # Whichever attempt scored best is what the lesson keeps.
        for key, value in best.items():
            lesson[key] = value
    return redone


def main(argv: list[str] | None = None, client=None) -> int:
    ap = argparse.ArgumentParser(description="Generate lesson content via Claude.")
    ap.add_argument("--unit", action="append", help="only this unit id (repeatable)")
    ap.add_argument("--level", action="append", type=int, help="only this HSK level")
    ap.add_argument("--all", action="store_true", help="regenerate complete units too")
    ap.add_argument("--limit", type=int, help="stop after this many units")
    ap.add_argument("--dry-run", action="store_true", help="report the plan, call nothing")
    ap.add_argument("--refresh", action="store_true",
                    help="ignore the cache for the units selected and generate "
                         "them again. Needed after a reorder: a lesson keeps the "
                         "same words, so the cache would hand back content "
                         "written for its old position in the curriculum.")
    ap.add_argument("--retries", type=int, default=2,
                    help="attempts to bring a lesson back into scope (default 2). "
                         "Each one is told every character the lesson has been "
                         "refused for, so they do not go in circles.")
    ap.add_argument("--no-retry", dest="retries", action="store_const", const=0,
                    help="don't re-ask a lesson that broke scope "
                         "(saves a call, loses the lesson)")
    args = ap.parse_args(argv)

    data = curriculum_source.load()
    targets = _select_units(data, args)
    if args.limit:
        targets = targets[: args.limit]

    if not targets:
        print("Nothing to generate — every unit in scope is already complete.")
        print("  (Add --all to regenerate finished units, overwriting their content.)")
        return 0

    n_lessons = sum(len(u.get("lessons") or []) for u in targets)
    print(f"{len(targets)} unit(s), {n_lessons} lesson(s) to generate.")

    if args.dry_run:
        for u in targets:
            missing = ", ".join(completeness.evaluate_unit(u).missing) or "complete"
            print(f"  {u['id']:<14} {len(u.get('lessons') or []):>3} lessons   missing: {missing}")
        print("\n(--dry-run) nothing generated")
        return 0

    if client is None:
        key = resolve_api_key()
        if not key:
            print("✗ No Anthropic API key found. This authoring tool needs one.")
            print("  Set it in any of these — the app checks all three:")
            print("    • the Me tab in the app (stored with your progress)")
            print("    • ANTHROPIC_API_KEY in .env at the repo root")
            print("    • export ANTHROPIC_API_KEY=... in your shell")
            print("  The app itself runs fine without a key — the committed live")
            print("  units are hand-authored, and drafts simply stay out of Learn.")
            return 1
        try:
            client = make_client(key)
        except ImportError:
            print("✗ anthropic SDK not installed. `pip install anthropic`.")
            return 1

    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    by_id = {u["id"]: u for u in data["units"]}
    promoted, still_draft, failed = [], [], []

    for unit in targets:
        print(f"\n▸ {unit['id']} — {unit.get('title', '')}")
        # A run that changes nothing must leave the file alone. Every lesson of
        # a unit can fail (an API outage, a bad schema, a rate limit), and
        # rewriting the unit anyway would demote curated content to draft on the
        # strength of a network error.
        was_live = curriculum_source.status_of(unit) == curriculum_source.STATUS_LIVE
        applied = 0
        for lesson in unit.get("lessons") or []:
            cache = GENERATED_DIR / f"{lesson['id']}.json"
            content = None if args.refresh else read_cache(cache, lesson)
            if content is not None:
                print(f"  • {lesson['id']}: cached")
            else:
                why = "refresh requested" if args.refresh else _miss_reason(cache, lesson)
                print(f"  ⟳ {lesson['id']}: {why}…")
                allowed = _allowed_words_upto(data, lesson["id"])
                try:
                    content = generate_lesson(client, lesson, allowed)
                except Exception as exc:  # noqa: BLE001 — one lesson must not sink the run
                    print(f"  ✗ {lesson['id']}: {exc}")
                    failed.append(lesson["id"])
                    continue
                write_cache(cache, lesson, content)
            apply_to_lesson(lesson, content)
            applied += 1

        if applied == 0:
            print("  ⊘ nothing generated — file left untouched")
            if not was_live:
                still_draft.append(unit["id"])
            continue

        # Promote only on BOTH gates: the content validates, and it is complete.
        by_id[unit["id"]] = unit
        unit_violations = _violations_for(data, by_id, unit)

        # One retry, naming what went out of scope. A lesson that cost a call
        # and is then discarded over a single word is the worst outcome
        # available; re-asking with the rejected characters usually clears it.
        if unit_violations and args.retries and client is not None:
            if _retry_lessons(
                client, data, by_id, unit, unit_violations, args.retries
            ):
                unit_violations = _violations_for(data, by_id, unit)

        slips = register_slips({"units": [unit]})
        if slips:
            print(f"  ! {len(slips)} Mainland word(s) in Taiwan content:")
            for slip in slips[:5]:
                swaps = ", ".join(f"{prc}→{tw}" for prc, tw in slip.found)
                print(f"      [{slip.where}] {swaps}")
            if len(slips) > 5:
                print(f"      … and {len(slips) - 5} more")
            print("      Not blocking. Edit content/units/ by hand, or re-run this")
            print("      unit with --unit to buy a fresh draft of those lessons.")

        report = completeness.evaluate_unit(unit)

        if unit_violations:
            print(f"  ✗ {len(unit_violations)} out-of-scope sentence(s) — left as draft:")
            for v in unit_violations[:5]:
                print(f"      [{v.where}] {v.text} → {' '.join(v.unknown)}")
            unit["status"] = curriculum_source.STATUS_DRAFT
            still_draft.append(unit["id"])
        elif report.complete:
            unit["status"] = curriculum_source.STATUS_LIVE
            promoted.append(unit["id"])
            print(f"  ✓ complete — promoted to live")
        else:
            unit["status"] = curriculum_source.STATUS_DRAFT
            still_draft.append(unit["id"])
            print(f"  ○ still draft — missing: {', '.join(report.missing)}")

        curriculum_source.write_unit(unit)

    print(f"\n{'=' * 60}")
    print(f"promoted to live : {len(promoted)}")
    print(f"still draft      : {len(still_draft)}")
    if failed:
        print(f"failed lessons   : {len(failed)} (re-run to retry; cached ones are skipped)")
    if PEAK_TOKENS:
        # The number that decides LESSON_BUDGET. Printed because every budget in
        # this pipeline that was estimated rather than measured turned out wrong,
        # and a truncation here is 185 calls' worth of wrong.
        headroom = round(100 * (1 - PEAK_TOKENS / LESSON_BUDGET))
        print(f"peak tokens      : {PEAK_TOKENS} of {LESSON_BUDGET} ({headroom}% headroom)")
        if headroom < 20:
            print("                   ⚠ tight — raise LESSON_BUDGET before a long run")
    print("\nRun `make coverage` for the full picture, then `make load-content`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
