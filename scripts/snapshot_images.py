from __future__ import annotations

import argparse
import sys

from _bootstrap import add_project_root

add_project_root()
from book_to_comic.artifact_materializer import snapshot_images


def main() -> int:
    parser = argparse.ArgumentParser(description="Snapshot generated image directories before one host image call.")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        path = snapshot_images(args.output)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
