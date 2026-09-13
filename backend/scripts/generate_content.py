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
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import completeness, curriculum_source  # noqa: E402
from app.config import REPO_ROOT
from app.llm import MODEL  # noqa: E402
from app.validation import (  # noqa: E402
    han_chars,
    placement_pool_chars,
    placement_pool_words,
    validate_curriculum,
)


GENERATED_DIR = REPO_ROOT / "content" / ".generated"

SYSTEM_PROMPT = """\
You are a Taiwanese Mandarin curriculum author. Write natural, everyday
Taiwan-register Mandarin for a HelloChinese-style learning app.

Hard rules:
- Traditional characters only. Taiwan usage and vocabulary (e.g. 腳踏車 not 自行車,
  捷運, 便當, 悠遊卡, 週末). Taiwan register particles where natural (喔/耶/啦).
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
  in `example_sentences`,
- 5 short drill sentences, each split into word tokens, each with a cloze_index
  pointing at a good word to blank out (prefer a new-vocab word),
- a 4–6 line dialogue set in a Taiwan daily-life scene using this vocab.
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

    class LessonContent(BaseModel):
        vocab_examples: list[VocabExample]
        grammar: list[Grammar]
        sentences: list[Sentence]
        dialogue: list[DialogueLine]

    return LessonContent


RETRY_NOTE = """\
Your previous attempt used characters the learner has not met yet, so it was \
rejected: {chars}

Rewrite the whole lesson. Keep the same vocabulary and the same teaching intent, \
but express every sentence using ONLY the allowed characters above. If a natural \
sentence needs a word you may not use, choose a different sentence rather than \
stretching the rule — a lesson that is slightly plainer is worth far more than \
one that gets thrown away."""


def generate_lesson(
    client, lesson: dict, allowed_words: list[str], rejected: list[str] | None = None
) -> dict:
    """One lesson's content. `rejected` re-asks, naming what went out of scope."""
    LessonContent = _make_models()
    prompt = _lesson_prompt(lesson, allowed_words)
    if rejected:
        prompt += "\n\n" + RETRY_NOTE.format(chars=" ".join(sorted(set(rejected))))
    response = client.messages.parse(
        model=MODEL,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        output_format=LessonContent,
    )
    parsed = response.parsed_output
    if parsed is None:
        raise RuntimeError(f"model did not return valid content for {lesson['id']}")
    return parsed.model_dump()


def _allowed_words_upto(skeleton: dict, lesson_id: str) -> list[str]:
    """Cumulative vocabulary available up to and including a lesson.

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
    if args.unit:
        units = [u for u in units if u["id"] in set(args.unit)]
    if args.level:
        units = [u for u in units if u.get("hsk_level") in set(args.level)]
    if args.all:
        return units
    return [
        u for u in units
        if curriculum_source.status_of(u) != curriculum_source.STATUS_LIVE
    ]


def _lesson_fingerprint(lesson: dict) -> list[str]:
    """The vocabulary ids this lesson teaches — what its content was written for."""
    return [v["id"] for v in (lesson.get("vocab") or []) if v.get("id")]


def read_cache(path: Path, lesson: dict) -> dict | None:
    """Cached content for this lesson, or None when it cannot be trusted.

    Lesson ids are positional — l_hsk2_01_1 is "the first lesson of the first
    HSK 2 unit", whatever words that unit currently holds. Re-theming regroups
    the words and keeps the ids, so a cache keyed on the id alone would hand back
    content written for an entirely different word set, print "cached", and
    produce a lesson whose examples have nothing to do with its vocabulary — for
    free, and looking like success. So the cache records what it was generated
    for, and a changed word set is a miss.

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
    return payload["_content"]


def write_cache(path: Path, lesson: dict, content: dict) -> None:
    path.write_text(
        json.dumps(
            {"_for_vocab": _lesson_fingerprint(lesson), "_content": content},
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


def _retry_lessons(client, data: dict, unit: dict, violations: list) -> int:
    """Regenerate just the lessons that broke scope. Returns how many were redone.

    Capped at this one attempt: if the model cannot stay in scope when told
    exactly which characters it may not use, asking again is paying to watch it
    fail. A lesson discarded over one word is the worst outcome available.
    """
    rejected: dict[str, set[str]] = {}
    for v in violations:
        rejected.setdefault(v.where.split()[0], set()).update(v.unknown)

    redone = 0
    for lesson in unit.get("lessons") or []:
        chars = rejected.get(lesson["id"])
        if not chars:
            continue
        print(f"  \u21bb {lesson['id']}: retrying — out of scope: {' '.join(sorted(chars))}")
        try:
            content = generate_lesson(
                client,
                lesson,
                _allowed_words_upto(data, lesson["id"]),
                rejected=sorted(chars),
            )
        except Exception as exc:  # noqa: BLE001 — a failed retry is not fatal
            print(f"  ✗ {lesson['id']}: retry failed: {exc}")
            continue
        # Overwrite the cache: the retry is the better version of this lesson.
        write_cache(GENERATED_DIR / f"{lesson['id']}.json", lesson, content)
        apply_to_lesson(lesson, content)
        redone += 1
    return redone


def main(argv: list[str] | None = None, client=None) -> int:
    ap = argparse.ArgumentParser(description="Generate lesson content via Claude.")
    ap.add_argument("--unit", action="append", help="only this unit id (repeatable)")
    ap.add_argument("--level", action="append", type=int, help="only this HSK level")
    ap.add_argument("--all", action="store_true", help="regenerate complete units too")
    ap.add_argument("--limit", type=int, help="stop after this many units")
    ap.add_argument("--dry-run", action="store_true", help="report the plan, call nothing")
    ap.add_argument("--no-retry", dest="retry", action="store_false",
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
            content = read_cache(cache, lesson)
            if content is not None:
                print(f"  • {lesson['id']}: cached")
            else:
                why = "words changed" if cache.is_file() else "generating"
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
        if unit_violations and args.retry and client is not None:
            if _retry_lessons(client, data, unit, unit_violations):
                unit_violations = _violations_for(data, by_id, unit)

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
    print("\nRun `make coverage` for the full picture, then `make load-content`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
