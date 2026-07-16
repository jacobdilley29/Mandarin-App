#!/usr/bin/env python3
"""Import CC-CEDICT into the `dictionary` table (spec §5).

CC-CEDICT provides Traditional + Simplified forms and pinyin. It is downloaded
and parsed at setup; the resulting DB lives under data/ (not committed).

Usage:
    python -m scripts.import_cedict                 # download + import
    python -m scripts.import_cedict --file PATH     # import a local .u8/.txt

Source (CC-CEDICT, CC BY-SA 4.0):
    https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.zip
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db  # noqa: E402

CEDICT_URL = "https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.zip"

# Line format:  Trad Simp [pin1 yin1] /gloss1/gloss2/
_LINE_RE = re.compile(r"^(\S+)\s+(\S+)\s+\[([^\]]*)\]\s+/(.*)/\s*$")


def parse_line(line: str) -> tuple[str, str, str, str] | None:
    line = line.rstrip("\n")
    if not line or line.startswith("#"):
        return None
    m = _LINE_RE.match(line)
    if not m:
        return None
    trad, simp, pinyin, gloss_block = m.groups()
    gloss = " / ".join(g for g in gloss_block.split("/") if g)
    return trad, simp, pinyin, gloss


def iter_entries(text: str):
    for line in text.splitlines():
        parsed = parse_line(line)
        if parsed:
            yield parsed


def download_text() -> str:
    print(f"Downloading CC-CEDICT from {CEDICT_URL} …")
    with urllib.request.urlopen(CEDICT_URL, timeout=120) as resp:  # noqa: S310
        raw = resp.read()
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".u8") or n.endswith(".txt"))
        return zf.read(name).decode("utf-8")


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def import_entries(text: str) -> int:
    db.init_db()
    conn = db.connect()
    n = 0
    try:
        conn.execute("DELETE FROM dictionary")
        batch = []
        for trad, simp, pinyin, gloss in iter_entries(text):
            batch.append((trad, simp, pinyin, gloss))
            if len(batch) >= 1000:
                _flush(conn, batch)
                n += len(batch)
                batch.clear()
        if batch:
            _flush(conn, batch)
            n += len(batch)
        conn.commit()
    finally:
        conn.close()
    return n


def _flush(conn, batch) -> None:
    conn.executemany(
        """INSERT INTO dictionary (traditional, simplified, pinyin, gloss)
           VALUES (?, ?, ?, ?)""",
        batch,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Import CC-CEDICT into SQLite.")
    ap.add_argument("--file", help="local CC-CEDICT .u8/.txt (skips download)")
    args = ap.parse_args()

    try:
        text = load_text(Path(args.file)) if args.file else download_text()
    except Exception as e:  # network / egress policy
        print(f"✗ could not obtain CC-CEDICT: {e}")
        print("  Download it manually and pass --file, or run this on a machine")
        print("  with direct internet access.")
        return 1

    n = import_entries(text)
    print(f"✓ imported {n:,} dictionary entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
