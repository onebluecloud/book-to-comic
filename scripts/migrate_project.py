from __future__ import annotations

import argparse
import json
import sys

from _bootstrap import add_project_root

add_project_root()
from book_to_comic.migrations import migrate_project


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate a project to schema 3.0 without inventing missing planning.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--to-version", default="3.0")
    args = parser.parse_args()
    try:
        result = migrate_project(args.project, to_version=args.to_version)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
