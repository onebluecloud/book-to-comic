from __future__ import annotations

import argparse
import sys

from _bootstrap import add_project_root

add_project_root()
from book_to_comic.artifact_materializer import init_project


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize an Artifact Materializer comic project.")
    parser.add_argument("--book", required=True)
    parser.add_argument("--project-dir", required=True)
    args = parser.parse_args()
    try:
        path = init_project(args.book, args.project_dir)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
