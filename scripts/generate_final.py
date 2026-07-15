from __future__ import annotations

import argparse
import json
import sys

from _bootstrap import add_project_root

add_project_root()
from book_to_comic.final_pipeline import generate_final_comic


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate final comic deliverables through a save-capable image backend.")
    parser.add_argument("project_dir")
    parser.add_argument("--backend", default="auto", choices=("auto", "codex-exec-image-worker"))
    parser.add_argument("--formats", default="pdf,cbz,epub,long-image,zip")
    parser.add_argument("--codex-bin")
    parser.add_argument("--width", type=int, default=1536)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--quality", default="high", choices=("medium", "high"))
    parser.add_argument("--image-selftest-timeout", type=int, default=300)
    args = parser.parse_args()

    try:
        result = generate_final_comic(
            args.project_dir,
            backend=args.backend,
            formats=args.formats,
            codex_bin=args.codex_bin,
            width=args.width,
            height=args.height,
            quality=args.quality,
            image_selftest_timeout_seconds=args.image_selftest_timeout,
        )
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
