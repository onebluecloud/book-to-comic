from __future__ import annotations

import argparse
import json
import sys

from _bootstrap import add_project_root

add_project_root()
from book_to_comic.artifact_materializer import materialize_image


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize one host-generated image into assets/candidates.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--kind", required=True, choices=("character-reference", "panel"))
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--version", required=True, type=int)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--panel-index", type=int)
    parser.add_argument("--reference-asset", action="append")
    parser.add_argument("--source")
    args = parser.parse_args()
    try:
        item = materialize_image(
            project=args.project,
            kind=args.kind,
            asset_id=args.asset_id,
            version=args.version,
            snapshot=args.snapshot,
            prompt=args.prompt,
            panel_index=args.panel_index,
            reference_assets=args.reference_asset or [],
            source=args.source,
        )
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(item, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
