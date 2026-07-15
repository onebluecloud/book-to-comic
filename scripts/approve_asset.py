from __future__ import annotations

import argparse
import json
import sys

from _bootstrap import add_project_root

add_project_root()
from book_to_comic.artifact_materializer import approve_asset


def main() -> int:
    parser = argparse.ArgumentParser(description="Approve a candidate image into its canonical asset path.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--qa-summary", required=True)
    args = parser.parse_args()
    try:
        item = approve_asset(args.project, args.asset_id, args.qa_summary)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(item, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
