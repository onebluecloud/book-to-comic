from __future__ import annotations

import argparse
import json
import sys

from _bootstrap import add_project_root

add_project_root()
from book_to_comic.project_layout import migrate_legacy_project


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate legacy episodes/EP01/episode.json into story/episode-001.json.")
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    try:
        result = migrate_legacy_project(args.project)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
