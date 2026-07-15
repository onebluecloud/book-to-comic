from __future__ import annotations

import json
import sys
import argparse

from _bootstrap import add_project_root

add_project_root()
from book_to_comic.image_backends import probe_image_backends


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe save-capable image backends.")
    parser.add_argument("project_dir", nargs="?")
    parser.add_argument("--selftest-image", action="store_true")
    args = parser.parse_args()
    report = probe_image_backends(project_dir=args.project_dir, run_image_selftest=args.selftest_image)
    sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
