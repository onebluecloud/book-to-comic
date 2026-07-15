"""Build the distributable skill ZIP with a hard exclusion list.

The v5.13.0 zip was assembled ad hoc and swallowed 111 build/ files plus
egg-info (2026-07 release audit P2-1). This script is the only sanctioned
packager: fixed exclusions, in-zip self-checks, SHA-256 output.

Usage:  python tools/build_release_zip.py [--out dist/]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE_DIRS = {".git", "dist", "build", "__pycache__", ".pytest_cache", ".ruff_cache", "node_modules"}
EXCLUDE_DIR_SUFFIXES = (".egg-info",)
EXCLUDE_FILES = {".gitignore"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".zip"}
TOP_LEVEL = "book-to-comic"


def _version() -> str:
    sys.path.insert(0, str(ROOT))
    import book_to_comic

    return book_to_comic.__version__


def _excluded(path: Path) -> bool:
    for part in path.parts:
        if part in EXCLUDE_DIRS or part.endswith(EXCLUDE_DIR_SUFFIXES):
            return True
    return path.name in EXCLUDE_FILES or path.suffix in EXCLUDE_SUFFIXES


# 严格的技能商店上传只接受这四类后缀,其余(含 .toml 与无后缀文件)会被静默剔除
# —— 2026-07-14 实测:pyproject.toml 与 LICENSE 被过滤,130 个 .py 全部保留。
PLATFORM_KEEP_SUFFIXES = {".py", ".json", ".md", ".txt"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "dist"))
    parser.add_argument("--date", default="", help="Datestamp for the file name (YYYYMMDD); required.")
    parser.add_argument(
        "--platform",
        action="store_true",
        help=(
            "Build a strict-uploader bundle: ship ONLY the suffixes such platforms accept "
            "(.py/.json/.md/.txt) so nothing gets silently filtered on upload. setup.py then "
            "carries install metadata in place of the stripped pyproject.toml."
        ),
    )
    args = parser.parse_args()
    if not args.date:
        print("--date YYYYMMDD is required (no ambient clock in the packager).", file=sys.stderr)
        return 2
    version = _version()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = "-redskill" if args.platform else ""
    out = out_dir / f"book-to-comic-skill-v{version}-{args.date}{suffix}.zip"

    files = [
        path
        for path in sorted(ROOT.rglob("*"))
        if path.is_file() and not _excluded(path.relative_to(ROOT))
    ]
    if args.platform:
        files = [p for p in files if p.suffix.lower() in PLATFORM_KEEP_SUFFIXES]
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, (Path(TOP_LEVEL) / path.relative_to(ROOT)).as_posix())

    # Self-checks: the packager refuses to emit a dirty or broken bundle.
    names = zipfile.ZipFile(out).namelist()
    problems = []
    if any(".." in name or name.startswith("/") for name in names):
        problems.append("path traversal entry")
    for marker in ("/build/", ".egg-info", "__pycache__", "/.git/"):
        if any(marker in name for name in names):
            problems.append(f"build residue: {marker}")
    # setup.py / LICENSE.md are the platform-survival pair: a restrictive skill-store upload strips
    # `.toml` and extension-less files (2026-07-14 measured — pyproject.toml and
    # LICENSE were filtered out, every .py/.json/.md/.txt survived). Without
    # setup.py the filtered bundle cannot `pip install` and the `book-to-comic`
    # command is never registered, so every SKILL.md command fails.
    required = [f"{TOP_LEVEL}/SKILL.md", f"{TOP_LEVEL}/setup.py", f"{TOP_LEVEL}/LICENSE.md"]
    if not args.platform:
        required.append(f"{TOP_LEVEL}/pyproject.toml")
    for entry in required:
        if entry not in names:
            problems.append(f"missing required entry: {entry}")
    if args.platform:
        # The whole point of the platform bundle is a silent-filter-free upload:
        # refuse to emit it if ANY entry would be stripped by the platform.
        strays = sorted(
            {n for n in names if Path(n).suffix.lower() not in PLATFORM_KEEP_SUFFIXES}
        )
        if strays:
            problems.append(
                "platform bundle would still be filtered on upload: " + ", ".join(strays[:8])
            )
    if not any(name.startswith(f"{TOP_LEVEL}/tests/") for name in names):
        problems.append("tests/ missing from bundle")
    if problems:
        out.unlink()
        print("Refusing to emit bundle: " + "; ".join(problems), file=sys.stderr)
        return 1
    digest = hashlib.sha256(out.read_bytes()).hexdigest().upper()
    print(json.dumps({"zip": str(out), "entries": len(names), "sha256": digest}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
