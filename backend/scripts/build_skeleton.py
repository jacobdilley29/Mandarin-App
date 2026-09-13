#!/usr/bin/env python3
"""Build the curriculum skeleton from the vendored HSK word lists (spec §5).

`generate_content.py` writes sentences *into* lessons that already exist; nothing
created the lessons themselves, which is why the app shipped 149 vocab items
against a 1,200-word HSK 1–4 target. This script closes that gap: it turns
content/wordlists/hsk{1..4}.json into units and lessons, merges them with the
hand-authored curriculum, and writes a skeleton `generate_content.py` can fill.

Pipeline, in order:

  1. Load the vendored lists (frequency-ordered).
  2. Apply content/taiwan_overrides.json — PRC→Taiwan word substitutions and
     Taiwan readings. The lists carry traditional characters but mainland
     vocabulary and mainland readings, so this step is not optional (spec §6).
  3. Drop anything already taught in the hand-authored curriculum, matching on
     `traditional`. Curated entries win: they carry Taiwan notes and examples,
     and `vocab.traditional` is UNIQUE so a duplicate would abort the load.
  4. Bin the remainder into units/lessons of `--per-lesson` words.
       --theme claude   ask Claude to group each level into Taiwan daily-life
                        themes and to settle unresolved readings in context
       --theme offline  deterministic frequency-ordered sets (no API key)
  5. Assign sort_order: levels ascend 1→4, and within a level the hand-authored
     themed units come before the generated ones.
  6. Tag each unit with its TOCFL level/band from content/tocfl_mapping.json.

Every input word must land in exactly one lesson; the script fails loudly if not.

Usage:
    python -m scripts.build_skeleton --theme offline
    ANTHROPIC_API_KEY=... python -m scripts.build_skeleton --theme claude
    python -m scripts.build_skeleton --report-readings   # audit only, no write

This is an authoring tool. It is NOT needed to run the app.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import curriculum_source, taiwanize  # noqa: E402
from app.config import REPO_ROOT
from app.llm import MODEL  # noqa: E402



CONTENT = REPO_ROOT / "content"
WORDLISTS = CONTENT / "wordlists"
OVERRIDES_PATH = CONTENT / "taiwan_overrides.json"
TOCFL_PATH = CONTENT / "tocfl_mapping.json"
CURRICULUM_PATH = CONTENT / "curriculum.json"
HSK1_POOL_PATH = CONTENT / "hsk1.json"
CACHE_DIR = CONTENT / ".generated"

LEVELS = (1, 2, 3, 4)

_TONED = set("āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜ")
_NON_HAN = re.compile(r"[^㐀-䶿一-鿿]")

# Second syllables that are genuinely neutral in Taiwan too — particles and
# suffixes, as opposed to the lexical words where Taiwan keeps a full tone.
_TRUE_NEUTRAL = {
    "de", "le", "ma", "ne", "ba", "zi", "men", "ge", "a", "o", "wa",
    "bu", "xia", "tou", "me", "xie", "jie", "mei", "di", "ge5",
}


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_wordlists() -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for level in LEVELS:
        path = WORDLISTS / f"hsk{level}.json"
        if not path.is_file():
            raise SystemExit(f"✗ missing word list: {path}")
        out[level] = load_json(path)["words"]
    return out


def _hsk1_pool() -> dict:
    return load_json(HSK1_POOL_PATH) if HSK1_POOL_PATH.is_file() else {}


def curated_words() -> dict[str, dict]:
    """Every word already taught by HAND, keyed on traditional form.

    Units this script generated are excluded on purpose. Counting them would
    make a second run see all 1,208 words as "already taught", place nothing,
    and then fail its own coverage assertion — the script has to be re-runnable,
    since that is how a word list refresh or a re-theme gets applied.
    """
    known: dict[str, dict] = {}
    for data in (curriculum_source.load(), _hsk1_pool()):
        for v in data.get("vocab", []):
            known[v["traditional"]] = v
        for unit in data.get("units", []):
            if unit.get("generated"):
                continue
            for lesson in unit.get("lessons", []):
                for v in lesson.get("vocab", []):
                    known[v["traditional"]] = v
    return known


# ---------------------------------------------------------------------------
# Taiwan overrides (spec §6)
# ---------------------------------------------------------------------------
def apply_overrides(words: list[dict], overrides: dict) -> tuple[list[dict], list[str]]:
    """Substitute PRC vocabulary and pin Taiwan readings over a whole list.

    The rules themselves live in app/taiwanize.py so that this script, the
    CC-CEDICT importer and anything else added later cannot drift apart on what
    "Taiwan usage" means. `overrides` is accepted for call compatibility but the
    table is read from content/taiwan_overrides.json by taiwanize itself.
    """
    out: list[dict] = []
    notes: list[str] = []
    for w in words:
        entry, entry_notes = taiwanize.normalize_entry(w)
        out.append(entry)
        notes.extend(entry_notes)
    return out, notes


unresolved_readings = taiwanize.unresolved_readings


# ---------------------------------------------------------------------------
# Binning into units and lessons
# ---------------------------------------------------------------------------
def slug(text: str, prefix: str) -> str:
    """A stable id from a Han title, falling back to a numeric suffix."""
    base = _NON_HAN.sub("", text)[:4] or "x"
    return f"{prefix}_{base}"


def vocab_entry(w: dict) -> dict:
    """A word in the curriculum's own vocab shape (see content/curriculum.json)."""
    item = {
        "id": "v_" + _NON_HAN.sub("", w["traditional"]),
        "traditional": w["traditional"],
        "pinyin": w["pinyin"],
        "gloss": w["gloss"],
        "hsk_level": w["hsk_level"],
        "taiwan_note": w.get("taiwan_note"),
    }
    if w.get("prc_form"):
        item["prc_form"] = w["prc_form"]
    return item


def bin_offline(words: list[dict], level: int, per_lesson: int,
                lessons_per_unit: int) -> list[dict]:
    """Deterministic fallback: frequency-ordered sets, no API key needed."""
    lessons = [words[i:i + per_lesson] for i in range(0, len(words), per_lesson)]
    units = []
    for ui, start in enumerate(range(0, len(lessons), lessons_per_unit), start=1):
        chunk = lessons[start:start + lessons_per_unit]
        units.append({
            "id": f"u_hsk{level}_{ui:02d}",
            "title": f"HSK {level} 詞彙 {ui}",
            "subtitle": f"HSK {level} vocabulary · set {ui}",
            "hsk_level": level,
            "generated": True,
            # Staged, never taught. A unit built from a word list has no
            # sentences, dialogue or grammar, so it fails the required
            # completeness checks and the gate keeps it out of Learn until
            # generate_content has filled it in. See app/completeness.py.
            "status": curriculum_source.STATUS_DRAFT,
            "lessons": [
                {
                    "id": f"l_hsk{level}_{ui:02d}_{li}",
                    "title": f"詞彙 {ui}–{li}",
                    "sort_order": li,
                    "vocab": [vocab_entry(w) for w in group],
                    "grammar": [],
                    "dialogue": [],
                    "sentences": [],
                }
                for li, group in enumerate(chunk, start=1)
            ],
        })
    return units


THEME_SYSTEM = """\
You are a Taiwanese Mandarin curriculum designer. You group vocabulary into
themed lessons for a HelloChinese-style app aimed at daily life in Taiwan.

Hard rules:
- Traditional characters, Taiwan usage and register throughout.
- Group by situation a learner actually meets in Taiwan (便利商店, 夜市, 捷運,
  看醫生, 租房子, 辦手機…), not by part of speech or textbook category.
- Every word you are given must appear in exactly one lesson. Never drop a word,
  never invent one, never repeat one.
- Unit titles in Traditional Chinese; subtitles in plain English.
"""


def theme_prompt(words: list[dict], level: int, existing: list[str],
                 per_lesson: int) -> str:
    lines = "\n".join(
        f"  {w['traditional']} ({w['pinyin']}): {w['gloss'][:60]}" for w in words
    )
    flagged = [w for w in words if len(w.get("readings") or []) > 1]
    reading_note = ""
    if flagged:
        listed = "\n".join(
            f"  {w['traditional']}: {' / '.join(w['readings'])} (currently {w['pinyin']})"
            for w in flagged[:60]
        )
        reading_note = f"""

Some of these are 多音字 with more than one reading. For each, confirm the
reading a Taiwan learner should be taught at this level, in `reading_fixes`:
{listed}"""

    return f"""\
Group these {len(words)} HSK {level} words into themed units for life in Taiwan.
About {per_lesson} words per lesson, 2-4 lessons per unit.

These themes already exist in the curriculum — complement them, do not duplicate:
{', '.join(existing)}

Words:
{lines}{reading_note}

Return JSON matching the schema. Every word above must appear exactly once
across all lessons.
"""


def _theme_models():
    from pydantic import BaseModel

    class Lesson(BaseModel):
        title: str
        words: list[str]

    class Unit(BaseModel):
        title: str
        subtitle: str
        lessons: list[Lesson]

    class ReadingFix(BaseModel):
        traditional: str
        pinyin: str
        why: str

    class LevelPlan(BaseModel):
        units: list[Unit]
        reading_fixes: list[ReadingFix]

    return LevelPlan


def resolve_api_key() -> str | None:
    """The Anthropic key from wherever the user actually put it.

    The Me tab in the app (progress.db), .env, or the shell — the precedence
    app.conversation.effective_api_key already implements for the Talk tab.
    This used to call anthropic.Anthropic() bare, which reads the environment
    only, so a key entered in the app themed nothing and failed on auth.
    """
    from app import conversation, db

    try:
        conn = db.connect()
    except Exception:  # noqa: BLE001 — a fresh checkout has no database yet
        return conversation.effective_api_key(None)
    try:
        return conversation.effective_api_key(conn)
    finally:
        conn.close()


def _client():
    import anthropic

    key = resolve_api_key()
    return anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()


def theme_budget(word_count: int) -> int:
    """`max_tokens` for one level's theming call, scaled to the level's size.

    This was a flat 16000, which is a guess that fits the smallest level and
    nothing else: HSK 4 is 590 words against HSK 1's 106, and the plan for it is
    proportionally longer — while adaptive thinking draws from the same budget,
    and a grouping problem gets harder, not easier, with more words to place.

    A truncated response is the worst shape of failure here, because it does not
    look like truncation: the parse simply yields nothing and the error says the
    model returned no plan, which reads like a model or key problem. So the
    budget scales, and _plan_from_response names truncation when it happens.
    """
    return max(16000, 6000 + word_count * 60)


def _plan_from_response(response, level: int):
    """The parsed plan, or an error that says what actually went wrong."""
    if response.parsed_output is not None:
        return response.parsed_output.model_dump()
    if getattr(response, "stop_reason", None) == "max_tokens":
        used = getattr(getattr(response, "usage", None), "output_tokens", "?")
        raise RuntimeError(
            f"HSK {level}: the plan was cut off at the token limit "
            f"({used} output tokens). Raise theme_budget(), or split the level "
            f"with --levels."
        )
    raise RuntimeError(
        f"HSK {level}: no plan came back (stop_reason="
        f"{getattr(response, 'stop_reason', 'unknown')})"
    )


def bin_claude(words: list[dict], level: int, existing: list[str],
               per_lesson: int, refresh: bool) -> tuple[list[dict], list[dict]]:
    """Ask Claude to theme a level. Cached per level so runs are resumable."""
    import anthropic

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"skeleton-hsk{level}.json"
    if cache.is_file() and not refresh:
        print(f"  • HSK {level}: cached plan, skipping API call")
        plan = load_json(cache)
    else:
        budget = theme_budget(len(words))
        print(f"  ⟳ HSK {level}: theming {len(words)} words (budget {budget} tokens)…")
        client = _client()
        # Streamed: a themed level is a long generation, and a non-streaming
        # request of this size can exceed the request timeout and fail for a
        # reason that has nothing to do with the plan.
        with client.messages.stream(
            model=MODEL,
            max_tokens=budget,
            thinking={"type": "adaptive"},
            system=THEME_SYSTEM,
            messages=[{"role": "user",
                       "content": theme_prompt(words, level, existing, per_lesson)}],
            output_format=_theme_models(),
        ) as stream:
            response = stream.get_final_message()
        plan = _plan_from_response(response, level)
        cache.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    by_word = {w["traditional"]: w for w in words}
    fixes = plan.get("reading_fixes", [])
    for fix in fixes:
        w = by_word.get(fix["traditional"])
        if w and _norm_pinyin(fix["pinyin"]) != _norm_pinyin(w["pinyin"]):
            w["pinyin"] = fix["pinyin"]
            w.pop("bopomofo", None)

    units, used = [], set()
    for ui, u in enumerate(plan["units"], start=1):
        lessons = []
        for li, l in enumerate(u["lessons"], start=1):
            picked = [by_word[t] for t in l["words"] if t in by_word and t not in used]
            used.update(w["traditional"] for w in picked)
            if not picked:
                continue
            lessons.append({
                "id": f"l_hsk{level}_{ui:02d}_{li}",
                "title": l["title"],
                "sort_order": li,
                "vocab": [vocab_entry(w) for w in picked],
                "grammar": [],
                "dialogue": [],
                "sentences": [],
            })
        if lessons:
            units.append({
                "id": f"u_hsk{level}_{ui:02d}",
                "title": u["title"],
                "subtitle": u["subtitle"],
                "hsk_level": level,
                "generated": True,
                "lessons": lessons,
            })

    # Claude may drop words; sweep the remainder into a final unit so coverage
    # is never silently incomplete.
    missed = [w for w in words if w["traditional"] not in used]
    if missed:
        print(f"    ! {len(missed)} word(s) unassigned by the model — sweeping up")
        units.extend(bin_offline(missed, level, per_lesson, lessons_per_unit=3))
        for i, u in enumerate(units[len(units) - 1:], start=len(units)):
            u["id"] = f"u_hsk{level}_rest{i}"
    return units, fixes


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------
def apply_readings_to_authored(existing: dict, overrides: dict) -> list[str]:
    """Apply the reading overrides to the hand-authored vocabulary too.

    The overrides are skipped for words already curated, because the curated
    entry wins on gloss, Taiwan note and example. Its *reading* should not win:
    the hand-authored content carries mainland neutral tones in places (晚上
    wǎnshang for Taiwan's wǎnshàng) and one outright error (好吃 as hào chī).
    Mutates `existing` in place; returns what changed.
    """
    changed: list[str] = []
    for unit in existing.get("units", []):
        for lesson in unit.get("lessons", []):
            for v in lesson.get("vocab", []):
                want, fixed = taiwanize.apply_reading(v["traditional"], v.get("pinyin"))
                if fixed:
                    changed.append(f"{v['traditional']} {v['pinyin']} → {want}")
                    v["pinyin"] = want
    return changed


def _report_stalled(stalled: list[int]) -> None:
    """Say loudly what was not re-themed, and what not to do about it.

    The expensive mistake is generating into a level that was never regrouped:
    its words move when the re-theme eventually succeeds, and the generation
    cache treats a changed word set as a miss, so that content is paid for twice.
    """
    if not stalled:
        return
    levels_txt = ", ".join(f"HSK {lv}" for lv in stalled)
    verb = "is" if len(stalled) == 1 else "are"
    print(f"\n! {levels_txt} could not be re-themed and {verb} unchanged.")
    print("  Re-run `make build-skeleton` to retry — levels that already succeeded")
    print("  are cached and cost nothing. Do NOT run generate-content for a stalled")
    print("  level yet: its words will be regrouped, and anything generated now is")
    print("  paid for twice.")


def _existing_generated(existing: dict, level: int) -> list[dict]:
    """This level's generated units as they stand, for a level that failed to re-theme."""
    return [
        u for u in existing.get("units", [])
        if u.get("generated") and (u.get("hsk_level") or 0) == level
    ]


def assemble(existing: dict, generated: dict[int, list[dict]], tocfl: dict) -> dict:
    """Merge hand-authored units with generated ones and assign sort_order.

    Ordering: **every** hand-authored unit comes first, in its existing order,
    then the generated units by ascending level. The previous version ordered by
    level first and put authored units ahead only *within* a level — which, since
    the authored units are HSK 2-4 and the generated ones start at HSK 1, put
    generated vocabulary sets at the very front of Learn. That is what got
    commit 08e90b7 reverted.

    The draft gate already stops an unfinished unit being taught whatever its
    sort_order, so this is belt and braces: even once a generated unit is
    completed and promoted, 便利商店 still opens the curriculum.
    """
    band = {lv["hsk_level"]: lv for lv in tocfl["levels"]}

    authored = [u for u in existing.get("units", []) if not u.get("generated")]
    authored.sort(key=lambda u: u.get("sort_order", 0))

    made: list[dict] = []
    for level in sorted(generated):
        made.extend(generated[level])

    ordered: list[dict] = []
    for order, unit in enumerate(authored + made, start=1):
        unit = dict(unit)
        unit["sort_order"] = order
        meta = band.get(unit.get("hsk_level") or 1)
        if meta:
            unit["tocfl_level"] = meta["tocfl_level"]
            unit["tocfl_band"] = meta["tocfl_band"]
        ordered.append(unit)

    out = dict(existing)
    out["units"] = ordered
    meta = dict(existing.get("meta", {}))
    meta["note"] = (
        "Graded curriculum for Taiwanese Mandarin, HSK 1→4, cross-tagged to TOCFL. "
        "Hand-authored themed units lead; units built from the vendored HSK word "
        "lists by backend/scripts/build_skeleton.py follow them as drafts, and are "
        "withheld from Learn until scripts/generate_content.py completes them. "
        "Traditional characters, Taiwan usage and readings (see "
        "content/taiwan_overrides.json)."
    )
    meta["built_by"] = "scripts/build_skeleton.py"
    out["meta"] = meta
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the curriculum skeleton.")
    ap.add_argument("--theme", choices=("claude", "offline"), default="claude",
                    help="how to group words into units (default: claude — "
                         "situation-based themes; 'offline' needs no key but "
                         "produces numbered frequency sets)")
    ap.add_argument("--per-lesson", type=int, default=6,
                    help="target new words per lesson (spec §3.1 says 5-8)")
    ap.add_argument("--lessons-per-unit", type=int, default=3)
    ap.add_argument("--levels", default="1,2,3,4",
                    help="comma-separated HSK levels to build")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be built, write nothing")
    ap.add_argument("--refresh", action="store_true",
                    help="ignore the cached Claude plans and re-theme")
    ap.add_argument("--report-readings", action="store_true",
                    help="audit reading selection and exit without writing")
    args = ap.parse_args(argv)

    levels = [int(x) for x in args.levels.split(",") if x.strip()]
    lists = load_wordlists()
    overrides = load_json(OVERRIDES_PATH)
    tocfl = load_json(TOCFL_PATH)
    existing = curriculum_source.load()
    curated = curated_words()

    all_words: list[dict] = []
    notes: list[str] = []
    for level in levels:
        words, level_notes = apply_overrides(lists[level], overrides)
        all_words.extend(words)
        notes.extend(level_notes)

    if args.report_readings:
        flagged = unresolved_readings(all_words)
        print(f"{len(flagged)} word(s) with an unsettled reading:\n")
        for f in flagged:
            print(f"  HSK{f['hsk_level']} {f['traditional']:6} {f['pinyin']:16} "
                  f"{','.join(f['why'])}")
        print("\nPin these under `readings` in content/taiwan_overrides.json, "
              "or resolve them with --theme claude.")
        return 0

    authored_fixes = apply_readings_to_authored(existing, overrides)
    if authored_fixes:
        print(f"Corrected {len(authored_fixes)} reading(s) in hand-authored vocab:")
        for f in authored_fixes:
            print(f"  {f}")

    print(f"Applied {len(notes)} Taiwan override(s) to the imported lists:")
    for n in notes[:12]:
        print(f"  {n}")
    if len(notes) > 12:
        print(f"  … and {len(notes) - 12} more")

    if args.theme == "claude" and not resolve_api_key():
        print("✗ --theme claude needs an Anthropic key. Put it in the Me tab, in")
        print("  .env as ANTHROPIC_API_KEY, or export it in your shell.")
        print("  Or group words without one:  make build-skeleton ARGS=\"--theme offline\"")
        return 1

    existing_themes = [u["title"] for u in existing["units"] if not u.get("generated")]

    generated: dict[int, list[dict]] = {}
    total_new = 0
    stalled: list[int] = []
    for level in levels:
        words, _ = apply_overrides(lists[level], overrides)
        fresh = [w for w in words if w["traditional"] not in curated]
        skipped = len(words) - len(fresh)
        if not fresh:
            print(f"HSK {level}: all {len(words)} words already taught")
            continue
        if args.theme == "claude":
            try:
                units, fixes = bin_claude(fresh, level, existing_themes,
                                          args.per_lesson, args.refresh)
            except Exception as exc:  # noqa: BLE001 — one level must not sink the run
                # Keep this level exactly as it is rather than dropping it.
                # Dropping would delete every unit at this level from the
                # curriculum — including generated lesson content that was paid
                # for — and the coverage check would then fail on words that are
                # not missing at all. Aborting the whole run is no better: it
                # throws away the levels that succeeded, and their plans cost
                # money too.
                print(f"  ✗ HSK {level}: {exc}")
                print(f"    leaving HSK {level} as it is; the other levels continue")
                stalled.append(level)
                kept = _existing_generated(existing, level)
                if kept:
                    generated[level] = kept
                continue
            if fixes:
                print(f"  HSK {level}: {len(fixes)} reading(s) settled by the model")
        else:
            units = bin_offline(fresh, level, args.per_lesson, args.lessons_per_unit)
        generated[level] = units
        total_new += len(fresh)
        print(f"HSK {level}: {len(fresh)} new words "
              f"({skipped} already taught) → {len(units)} units, "
              f"{sum(len(u['lessons']) for u in units)} lessons")

    merged = assemble(existing, generated, tocfl)

    # Coverage assertion — the whole point of the script.
    placed: list[str] = []
    for unit in merged["units"]:
        for lesson in unit["lessons"]:
            placed.extend(v["traditional"] for v in lesson["vocab"])
    dupes = {w for w in placed if placed.count(w) > 1}
    if dupes:
        print(f"✗ {len(dupes)} word(s) placed more than once: {sorted(dupes)[:10]}")
        return 1

    pool = {v["traditional"] for v in load_json(HSK1_POOL_PATH).get("vocab", [])}
    expected = {w["traditional"] for w in all_words if w["traditional"] not in pool}
    missing = expected - set(placed)
    if missing:
        print(f"✗ {len(missing)} word(s) never placed: {sorted(missing)[:10]}")
        return 1

    _report_stalled(stalled)

    if args.dry_run:
        print(f"\n(--dry-run) would write {len(merged['units'])} unit files; nothing written")
        return 1 if stalled else 0

    for unit in merged["units"]:
        curriculum_source.write_unit(unit)
    curriculum_source.write_manifest(
        merged.get("meta", {}), [u["id"] for u in merged["units"]]
    )

    lessons = sum(len(u["lessons"]) for u in merged["units"])
    n_draft = sum(
        1 for u in merged["units"]
        if curriculum_source.status_of(u) != curriculum_source.STATUS_LIVE
    )
    print(f"\n✓ wrote {len(merged['units'])} unit files to content/units/")
    print(f"  {len(merged['units'])} units, {lessons} lessons, "
          f"{len(placed)} vocab items ({total_new} newly added)")
    print(f"  {len(merged['units']) - n_draft} live · {n_draft} draft "
          f"— drafts are staged and NOT taught until completed")
    if args.theme == "offline":
        print("  Units are frequency-ordered sets. Re-run with --theme claude "
              "and an API key to group them into Taiwan daily-life themes.")
    print("  Next: python -m scripts.generate_content --level N   (adds sentences)")

    return 1 if stalled else 0


if __name__ == "__main__":
    raise SystemExit(main())
