"""Import an official TOCFL vocabulary list into content/wordlists/.

The curriculum is currently built from HSK 1-4 word lists with TOCFL labels
mapped on top (content/tocfl_mapping.json). That mapping carries its own
caveat: TOCFL's vocabulary targets run ahead of HSK at every band — Level 3
expects ~2,500 words against HSK 4's 1,200 cumulative — so the app covers a
TOCFL level's themes and grammar but only about half its words.

Fixing that is a change of *source data*, not of the pipeline. Drop the official
list in here, and build_skeleton bins it into units exactly as it bins the HSK
lists today.

    python -m scripts.import_tocfl novice.csv --level novice --dry-run
    python -m scripts.import_tocfl novice.csv --level novice

Where the file comes from: the Steering Committee for the Test Of
Proficiency-Huayu (SC-TOP) publishes the vocabulary lists for each level. Export
whatever they give you to CSV — .xlsx is read only if openpyxl happens to be
installed, and adding a spreadsheet dependency to run one import is not worth it.

What this does NOT do is take content from a commercial learning site. Word
lists are inventories of a language; lesson text is somebody's work. The app
writes its own sentences (scripts/generate_content.py).

Columns are detected by header, in Chinese or English, because every export is
shaped differently. --dry-run prints what it matched and writes nothing; run it
first, always.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import taiwanize  # noqa: E402
from app.config import REPO_ROOT  # noqa: E402

WORDLISTS = REPO_ROOT / "content" / "wordlists"

# Header synonyms, lowercased. Chinese first: the official exports are Chinese.
COLUMNS: dict[str, tuple[str, ...]] = {
    "traditional": ("詞語", "詞彙", "生詞", "漢字", "正體字", "繁體字", "word",
                    "traditional", "hanzi", "chinese", "vocabulary"),
    "pinyin": ("拼音", "漢語拼音", "pinyin", "reading", "romanization"),
    "gloss": ("英文", "英譯", "解釋", "釋義", "意思", "english", "gloss",
              "meaning", "definition", "translation"),
    "level": ("等級", "級別", "程度", "level", "band", "tocfl_level"),
    "pos": ("詞性", "part of speech", "pos", "word class"),
}

# One word per line, so anything with spaces or punctuation is a phrase or a
# stray header row rather than an entry.
HAN = re.compile(r"^[㐀-䶿一-鿿]+$")


def _norm_header(value: str) -> str:
    return unicodedata.normalize("NFKC", (value or "")).strip().lower()


def detect_columns(header: list[str]) -> dict[str, int]:
    """Map our field names onto this file's column indexes.

    Exact match first, then substring, so both "拼音" and "漢語拼音(Pinyin)"
    land on the same field without the caller configuring anything.
    """
    cleaned = [_norm_header(h) for h in header]
    found: dict[str, int] = {}

    for field, names in COLUMNS.items():
        for i, cell in enumerate(cleaned):
            if cell in names:
                found[field] = i
                break
        if field in found:
            continue
        for i, cell in enumerate(cleaned):
            if cell and any(n in cell for n in names):
                found[field] = i
                break
    return found


def read_rows(path: Path) -> list[list[str]]:
    """Rows from a CSV/TSV file, or an .xlsx if openpyxl is installed."""
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        try:
            import openpyxl
        except ImportError:
            raise SystemExit(
                f"✗ {path.name} is a spreadsheet and openpyxl is not installed.\n"
                "  Open it and 'Save As' CSV, then import that — one less dependency."
            )
        sheet = openpyxl.load_workbook(path, read_only=True, data_only=True).active
        return [["" if c is None else str(c) for c in row] for row in sheet.values]

    text = path.read_text(encoding="utf-8-sig", errors="replace")
    dialect_delim = "\t" if path.suffix.lower() in (".tsv", ".tab") else None
    if dialect_delim is None:
        sample = text[:4096]
        dialect_delim = "\t" if sample.count("\t") > sample.count(",") else ","
    return [row for row in csv.reader(text.splitlines(), delimiter=dialect_delim) if row]


def parse(path: Path, level: str) -> tuple[list[dict], list[str]]:
    """Rows -> normalised word entries, plus notes on what was changed or dropped."""
    rows = read_rows(path)
    if not rows:
        raise SystemExit(f"✗ {path} is empty")

    cols = detect_columns(rows[0])
    if "traditional" not in cols:
        raise SystemExit(
            f"✗ could not find a word column in {path.name}.\n"
            f"  Header row was: {rows[0]}\n"
            f"  Rename the column to one of: {', '.join(COLUMNS['traditional'][:6])}"
        )

    notes: list[str] = [f"columns matched: {', '.join(sorted(cols))}"]
    words: list[dict] = []
    seen: set[str] = set()
    skipped = 0

    def cell(row: list[str], field: str) -> str:
        i = cols.get(field)
        return (row[i].strip() if i is not None and i < len(row) else "")

    for row in rows[1:]:
        raw = cell(row, "traditional")
        if not raw:
            continue
        # The lists are Traditional already, but running the Taiwan conversion
        # costs nothing and catches a Simplified stray in a mixed export.
        word = taiwanize.to_traditional_tw(raw)
        if not HAN.match(word):
            skipped += 1
            continue
        if word in seen:
            continue
        seen.add(word)

        # A supplied reading is kept unless a Taiwan override overrules it
        # (垃圾 lèsè, 星期 xīngqí); with no column, derive it.
        reading, pinned = taiwanize.apply_reading(word, cell(row, "pinyin") or None)
        if pinned:
            notes.append(f"reading {word} → {reading}")

        entry = {
            "traditional": word,
            "pinyin": reading,
            "gloss": cell(row, "gloss"),
            "tocfl_level": cell(row, "level") or level,
            "frequency": len(words) + 1,  # file order: these lists are graded
        }
        if pos := cell(row, "pos"):
            entry["pos"] = [p.strip() for p in re.split(r"[,/、]", pos) if p.strip()]
        words.append(entry)

    if skipped:
        notes.append(f"skipped {skipped} row(s) that were not a single word")
    return words, notes


def existing_words() -> set[str]:
    """Everything the current lists already carry, to report the overlap."""
    out: set[str] = set()
    for path in sorted(WORDLISTS.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for w in data.get("words", []):
            if t := w.get("traditional"):
                out.add(t)
    return out


def _show(path: Path) -> str:
    """Repo-relative when it is in the repo, absolute otherwise — never raises."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("path", type=Path, help="the downloaded list (CSV/TSV/XLSX)")
    ap.add_argument("--level", required=True,
                    help="TOCFL level this file is, e.g. novice, 1, 2, 3")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what was parsed and write nothing")
    args = ap.parse_args(argv)

    if not args.path.is_file():
        raise SystemExit(f"✗ no such file: {args.path}")

    words, notes = parse(args.path, args.level)
    if not words:
        raise SystemExit("✗ no usable rows found — check --dry-run output and the header row")

    already = existing_words()
    overlap = [w["traditional"] for w in words if w["traditional"] in already]

    print(f"{args.path.name} → TOCFL {args.level}: {len(words)} word(s)")
    for note in notes[:12]:
        print(f"  · {note}")
    print(f"  · {len(overlap)} already in the current lists, "
          f"{len(words) - len(overlap)} new")
    missing_gloss = sum(1 for w in words if not w["gloss"])
    if missing_gloss:
        print(f"  ! {missing_gloss} word(s) have no English gloss — generation "
              f"needs one; add a gloss column or they will need CC-CEDICT")
    print("\n  sample:")
    for w in words[:5]:
        print(f"    {w['traditional']:6} {w['pinyin']:12} {w['gloss'][:40]}")

    slug = re.sub(r"[^a-z0-9]+", "", args.level.lower()) or "x"
    out_path = WORDLISTS / f"tocfl_{slug}.json"

    if args.dry_run:
        print(f"\n(--dry-run) would write {_show(out_path)}")
        return 0

    WORDLISTS.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "meta": {
                    "tocfl_level": args.level,
                    "standard": "TOCFL",
                    "count": len(words),
                    "source": args.path.name,
                    "note": "Imported by scripts/import_tocfl.py. Taiwan readings "
                            "applied from content/taiwan_overrides.json — never "
                            "edit this file to fix one, edit the overrides.",
                },
                "words": words,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"\n✓ wrote {_show(out_path)}")
    print("  Next: git diff to review it, then build the units from it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
