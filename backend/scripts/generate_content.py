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

The curriculum is ~200 lessons after scripts/build_skeleton.py runs, so
generate in chunks and validate between them:

Usage:
    ANTHROPIC_API_KEY=... python -m scripts.generate_content --level 1
    python -m scripts.generate_content --level 2 --limit 20
    python -m scripts.generate_content --from-lesson l_hsk3_04_2
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

from app.config import REPO_ROOT  # noqa: E402
from app.validation import validate_curriculum  # noqa: E402

MODEL = "claude-opus-5"
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
- Pinyin uses tone marks (diacritics), Taiwan readings where they differ
  (星期 xīngqí, 垃圾 lèsè, 和 hàn). Taiwan keeps full tones where the mainland
  standard neutralises them: 朋友 péngyǒu, 學生 xuéshēng, 喜歡 xǐhuān.
- Keep sentences short and level-appropriate for the lesson's HSK level (1–4).
- Avoid erhua (兒化); it is a mainland feature.
"""


def _lesson_prompt(lesson: dict, allowed_words: list[str]) -> str:
    vocab_lines = "\n".join(
        f"  - {v['traditional']} ({v['pinyin']}): {v['gloss']}" for v in lesson["vocab"]
    )
    return f"""\
Lesson: {lesson['title']}

New vocabulary this lesson:
{vocab_lines}

ALLOWED characters come from these words (plus the standard function-word list):
{' '.join(sorted(set(''.join(allowed_words))))}

Write, as JSON matching the provided schema:
- one grammar point that uses this lesson's vocab, with 3 example sentences,
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
        examples: list[Example]

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

    class LessonContent(BaseModel):
        grammar: list[Grammar]
        sentences: list[Sentence]
        dialogue: list[DialogueLine]

    return LessonContent


def generate_lesson(client, lesson: dict, allowed_words: list[str]) -> dict:
    LessonContent = _make_models()
    response = client.messages.parse(
        model=MODEL,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _lesson_prompt(lesson, allowed_words)}],
        output_format=LessonContent,
    )
    parsed = response.parsed_output
    if parsed is None:
        raise RuntimeError(f"model did not return valid content for {lesson['id']}")
    return parsed.model_dump()


def _allowed_words_upto(skeleton: dict, lesson_id: str) -> list[str]:
    """Cumulative vocabulary words available up to and including a lesson."""
    words: list[str] = []
    units = sorted(skeleton["units"], key=lambda u: u.get("sort_order", 0))
    for unit in units:
        for lesson in sorted(unit["lessons"], key=lambda l: l.get("sort_order", 0)):
            words.extend(v["traditional"] for v in lesson.get("vocab", []))
            if lesson["id"] == lesson_id:
                return words
    return words


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate lesson content via Claude.")
    ap.add_argument("--skeleton", default=str(REPO_ROOT / "content" / "curriculum.json"),
                    help="skeleton curriculum JSON (units + lessons + vocab)")
    ap.add_argument("--lesson", help="only (re)generate this lesson id")
    ap.add_argument("--level", type=int,
                    help="only generate lessons in units of this HSK level")
    ap.add_argument("--from-lesson",
                    help="skip until this lesson id, then generate onwards")
    ap.add_argument("--limit", type=int,
                    help="stop after generating this many lessons")
    ap.add_argument("--skip-existing", action="store_true",
                    help="leave lessons that already have sentences alone")
    ap.add_argument("--out", default=str(REPO_ROOT / "content" / "curriculum.json"))
    args = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("✗ ANTHROPIC_API_KEY not set. This authoring tool needs an API key.")
        print("  The app itself runs fine without it using the committed content.")
        return 1

    try:
        import anthropic
    except ImportError:
        print("✗ anthropic SDK not installed. `pip install anthropic` (Phase 5 dep).")
        return 1

    skeleton = json.loads(Path(args.skeleton).read_text(encoding="utf-8"))
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    client = anthropic.Anthropic()

    # Walk in curriculum order so the cumulative vocabulary constraint below is
    # the one the learner actually experiences.
    units = sorted(skeleton["units"], key=lambda u: u.get("sort_order", 0))
    reached = args.from_lesson is None
    generated = 0

    for unit in units:
        if args.level and unit.get("hsk_level") != args.level:
            continue
        for lesson in sorted(unit["lessons"], key=lambda l: l.get("sort_order", 0)):
            if args.lesson and lesson["id"] != args.lesson:
                continue
            if not reached:
                if lesson["id"] != args.from_lesson:
                    continue
                reached = True
            if args.skip_existing and lesson.get("sentences"):
                continue
            if args.limit is not None and generated >= args.limit:
                print(f"• reached --limit {args.limit}; stopping")
                break

            cache = GENERATED_DIR / f"{lesson['id']}.json"
            if cache.is_file() and not args.lesson:
                print(f"• {lesson['id']}: cached, skipping")
                content = json.loads(cache.read_text(encoding="utf-8"))
            else:
                print(f"⟳ {lesson['id']} (HSK {unit.get('hsk_level')}): generating…")
                allowed = _allowed_words_upto(skeleton, lesson["id"])
                content = generate_lesson(client, lesson, allowed)
                cache.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
                generated += 1
            lesson["grammar"] = content["grammar"]
            lesson["sentences"] = content["sentences"]
            lesson["dialogue"] = content["dialogue"]

    result = validate_curriculum(skeleton)
    if not result.ok:
        print(f"✗ {len(result.violations)} vocab violation(s) in generated content:")
        for v in result.violations:
            print(f"    [{v.where}] {v.text} → unknown: {' '.join(v.unknown)}")
        print("Fix or delete the offending cached lesson(s) and re-run.")
        return 1

    Path(args.out).write_text(json.dumps(skeleton, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
