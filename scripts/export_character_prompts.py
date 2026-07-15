from __future__ import annotations

import argparse
import json
import sys

from _bootstrap import add_project_root

add_project_root()
from book_to_comic.character_qa import export_character_prompts


def main() -> int:
    parser = argparse.ArgumentParser(description="Export no-text character reference prompts.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    try:
        result = export_character_prompts(args.project, output_dir=args.output_dir)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
