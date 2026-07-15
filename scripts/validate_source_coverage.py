from __future__ import annotations

import argparse
import json
import sys

from _bootstrap import add_project_root

add_project_root()
from book_to_comic.story_ir import validate_source_coverage


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate source coverage and drawable panel contracts.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--min-source-coverage", type=float, default=0.9)
    parser.add_argument("--max-balloon-overflow-rate", type=float, default=0.01)
    args = parser.parse_args()
    try:
        report = validate_source_coverage(
            args.project,
            min_source_coverage=args.min_source_coverage,
            max_balloon_overflow_rate=args.max_balloon_overflow_rate,
        )
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
