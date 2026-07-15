from __future__ import annotations

import argparse
import json
import sys

from _bootstrap import add_project_root

add_project_root()
from book_to_comic.visual_distinctiveness import validate_distinctiveness


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate local JSON-only cross-project visual distinctiveness.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--against", action="append", help="Previous project directory to compare against. Repeat for multiple baselines.")
    args = parser.parse_args()
    try:
        report = validate_distinctiveness(args.project, against=args.against)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
