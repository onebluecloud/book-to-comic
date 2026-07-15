from __future__ import annotations

import argparse
import json
import sys

from _bootstrap import add_project_root

add_project_root()
from book_to_comic.page_qa import validate_page_plan


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate comic page plan, panel assignment, and page rhythm.")
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    try:
        report = validate_page_plan(args.project)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
