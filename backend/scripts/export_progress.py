"""Export all learner progress to JSON.

    python -m scripts.export_progress > progress.json
    python -m scripts.export_progress -o progress.json

The output is the portable copy of everything that matters: carry this one file
to a new machine and `import_progress` reconstructs the app's state.
"""

from __future__ import annotations

import argparse
import json
import sys

from app import backup


def main() -> int:
    parser = argparse.ArgumentParser(description="Export learner progress as JSON.")
    parser.add_argument("-o", "--output", help="Write to this file (default: stdout).")
    args = parser.parse_args()

    payload = backup.export_progress()
    text = json.dumps(payload, ensure_ascii=False, indent=1)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(text)
        rows = sum(len(v) for v in payload["tables"].values())
        print(f"Wrote {rows} rows to {args.output}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
