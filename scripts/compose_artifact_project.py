from __future__ import annotations

import argparse
import json
import sys

from _bootstrap import add_project_root

add_project_root()
from book_to_comic.artifact_materializer import compose_artifact_project


def main() -> int:
    parser = argparse.ArgumentParser(description="Compose approved Artifact Materializer assets into final deliverables.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--mode", default="comic-page", choices=("comic-page", "long-scroll", "card", "review"))
    args = parser.parse_args()
    try:
        result = compose_artifact_project(args.project, mode=args.mode)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({key: str(value) for key, value in result.items()}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
