from __future__ import annotations

import argparse
import json
import sys

from _bootstrap import add_project_root

add_project_root()
from book_to_comic.story_ir import build_story_ir


def main() -> int:
    parser = argparse.ArgumentParser(description="Build story_ir and drawable panel contracts.")
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    try:
        result = build_story_ir(args.project)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
