from __future__ import annotations

import argparse
import json
import sys

from _bootstrap import add_project_root

add_project_root()
from book_to_comic.visual_contract import build_visual_contract


def main() -> int:
    parser = argparse.ArgumentParser(description="Build visual state locks and a prompt-ready reference pack.")
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    try:
        result = build_visual_contract(args.project)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
