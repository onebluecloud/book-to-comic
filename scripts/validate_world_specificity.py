from __future__ import annotations

import argparse
import json
import sys

from _bootstrap import add_project_root

add_project_root()
from book_to_comic.world_qa import validate_world_specificity


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate world model specificity and generic fallback density.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--against", action="append")
    args = parser.parse_args()
    try:
        report = validate_world_specificity(args.project, against=args.against)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
