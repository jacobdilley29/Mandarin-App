"""Word lookup for tapping a character in a sentence (spec §5).

Reading a dialogue or a passage, you hit a word you don't know. The choice is
to guess, or to leave the lesson and look it up — and leaving is how reading
practice turns into dictionary practice. So a tap gives the word, its reading
and its meaning, in place.

**The curriculum is the first source, not CC-CEDICT.** The app's own vocab table
holds every word it teaches, with the Taiwan reading it taught (銀行 yínháng, 和
hàn) and zhuyin transcribed from that reading. CC-CEDICT is broader but
Mainland-oriented, so it disagrees on exactly the words this app is careful
about. Looking there first would show the learner one reading in the lesson and
a different one on tap. CC-CEDICT fills the gaps and is optional: it is a
download that may never have been run, and everything here works without it.

Segmentation is done server-side for a whole string at once, rather than one
request per tap: 我要喝水 is four characters but three words, and 便利商店 is one.
Greedy longest-match against what the app knows, which is the right notion of
"word" here — it matches what the learner has been taught, so the boundaries
agree with the lessons.
"""

from __future__ import annotations

import re
import sqlite3

_HAN = re.compile(r"[㐀-䶿一-鿿]")

# The longest word worth trying. Curriculum entries are 1-4 characters
# (便利商店); anything longer is a phrase, and matching it would swallow words
# the learner does know.
MAX_WORD = 4


def _han(ch: str) -> bool:
    return bool(_HAN.match(ch))


def lookup(conn: sqlite3.Connection, word: str) -> dict | None:
    """One word, from the curriculum if it teaches it, else from CC-CEDICT."""
    row = conn.execute(
        "SELECT traditional, pinyin, zhuyin, gloss FROM vocab WHERE traditional = ?",
        (word,),
    ).fetchone()
    if row:
        return {
            "text": row["traditional"],
            "pinyin": row["pinyin"],
            "zhuyin": row["zhuyin"],
            "gloss": row["gloss"],
            "source": "curriculum",
        }

    try:
        row = conn.execute(
            """SELECT traditional, pinyin, pinyin_tw, zhuyin, gloss FROM dictionary
               WHERE traditional = ? LIMIT 1""",
            (word,),
        ).fetchone()
    except sqlite3.Error:
        return None  # no dictionary table yet — the import is optional
    if not row:
        return None
    return {
        "text": row["traditional"],
        "pinyin": row["pinyin_tw"] or row["pinyin"],
        "zhuyin": row["zhuyin"],
        "gloss": row["gloss"],
        "source": "cedict",
    }


def _known(conn: sqlite3.Connection) -> set[str]:
    """Every word the app can define, for segmentation."""
    words = {r["traditional"] for r in conn.execute("SELECT traditional FROM vocab")}
    try:
        words |= {
            r["traditional"]
            for r in conn.execute(
                f"SELECT DISTINCT traditional FROM dictionary "
                f"WHERE length(traditional) <= {MAX_WORD}"
            )
        }
    except sqlite3.Error:
        pass  # CC-CEDICT not imported; the curriculum alone still segments
    return words


def annotate(conn: sqlite3.Connection, text: str) -> list[dict]:
    """Split text into tappable spans, each with its reading and gloss.

    Done for the whole string in one go so a tap is instant and offline — a
    request per tap would put a spinner between the learner and a word they are
    mid-sentence on.

    Runs that aren't Han (punctuation, latin, spaces) come back as plain spans
    with no entry, as do Han words nothing can define.
    """
    known = _known(conn)
    out: list[dict] = []
    i = 0

    def push_plain(ch: str) -> None:
        if out and out[-1].get("entry") is None and out[-1].get("plain"):
            out[-1]["text"] += ch
        else:
            out.append({"text": ch, "entry": None, "plain": True})

    while i < len(text):
        ch = text[i]
        if not _han(ch):
            push_plain(ch)
            i += 1
            continue

        for size in range(min(MAX_WORD, len(text) - i), 0, -1):
            candidate = text[i : i + size]
            if candidate in known:
                entry = lookup(conn, candidate)
                out.append({"text": candidate, "entry": entry, "plain": False})
                i += size
                break
        else:
            # A Han character nothing defines: still its own span, so the
            # sentence renders identically whether or not a lookup exists.
            out.append({"text": ch, "entry": None, "plain": False})
            i += 1

    return out
