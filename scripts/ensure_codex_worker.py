from __future__ import annotations

import argparse
import json
import sys

from _bootstrap import add_project_root

add_project_root()
from book_to_comic.codex_cli_bootstrap import ensure_codex_cli
from book_to_comic.codex_image_worker import run_codex_exec_image_selftest


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure a launchable Codex CLI for book-to-comic image workers.")
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--codex-bin")
    parser.add_argument("--selftest-image", action="store_true")
    args = parser.parse_args()
    report = ensure_codex_cli(install=args.install, codex_bin=args.codex_bin)
    if args.selftest_image:
        selected_bin = report.get("selected_bin")
        if selected_bin:
            report["image_selftest"] = run_codex_exec_image_selftest(codex_bin=str(selected_bin))
        else:
            report["image_selftest"] = {
                "attempted": False,
                "ok": False,
                "reason": "No launchable Codex CLI was selected.",
            }
    sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
