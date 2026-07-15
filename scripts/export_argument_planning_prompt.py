from __future__ import annotations

import argparse
import json
import sys

from _bootstrap import add_project_root

add_project_root()
from book_to_comic.argument_map import export_argument_planning_prompt


def main() -> int:
    parser = argparse.ArgumentParser(description="Export a planning prompt for argument_map.json.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        result = export_argument_planning_prompt(args.project, output=args.output)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
