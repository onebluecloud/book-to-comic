from __future__ import annotations

import argparse
import json
import sys

from _bootstrap import add_project_root

add_project_root()
from book_to_comic.story_gate import StoryGateError, validate_story_gate


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate narrative story gates before final composition.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--require-llm-gate", action="store_true")
    args = parser.parse_args()
    try:
        report = validate_story_gate(args.project, require_llm_gate=args.require_llm_gate)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError, StoryGateError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
