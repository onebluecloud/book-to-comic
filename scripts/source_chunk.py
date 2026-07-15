from __future__ import annotations

import argparse
import sys

from _bootstrap import add_project_root

add_project_root()
from book_to_comic.story_ir import source_chunk_project


def main() -> int:
    parser = argparse.ArgumentParser(description="Split source/raw_text.txt into auditable source chunks.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--input")
    parser.add_argument("--chapter-id", default="CH1")
    parser.add_argument("--max-chars", type=int, default=1400)
    args = parser.parse_args()
    try:
        payload = source_chunk_project(
            args.project,
            input_path=args.input,
            chapter_id=args.chapter_id,
            max_chars=args.max_chars,
        )
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {len(payload['chunks'])} source chunk(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
