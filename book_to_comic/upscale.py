"""Optional local upscaling for approved panels.

Publish targets (1080-wide cards, print PDF) want more pixels than some host
image tools emit. This module upscales approved panels with a LOCAL
Real-ESRGAN-family executable if the user has one; it never downloads models
or requires a GPU by policy (ncnn-vulkan builds run on integrated graphics).

Resolution order for the upscaler binary:
1. ``BOOK_TO_COMIC_UPSCALER`` -- explicit path to an executable
2. ``realesrgan-ncnn-vulkan`` / ``realesrgan-ncnn-vulkan.exe`` on PATH

Without a binary the command reports clearly and does nothing; upscaling is an
explicit quality option, not a silent dependency.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image

UPSCALER_ENV = "BOOK_TO_COMIC_UPSCALER"
UPSCALER_NAMES = ("realesrgan-ncnn-vulkan", "realesrgan-ncnn-vulkan.exe", "realesrgan")
TARGET_SHORT_SIDE = 1024


def find_upscaler() -> Path | None:
    explicit = os.environ.get(UPSCALER_ENV)
    if explicit:
        path = Path(explicit)
        if path.is_file():
            return path
    for name in UPSCALER_NAMES:
        hit = shutil.which(name)
        if hit:
            return Path(hit)
    return None


def upscale_project_panels(
    project_dir: str | Path,
    *,
    scale: int = 2,
    only_below_short_side: int | None = TARGET_SHORT_SIDE,
) -> dict[str, Any]:
    """Upscale approved panels in place, backing originals up first.

    ``only_below_short_side`` skips panels that are already big enough; pass
    None to force-upscale everything.
    """
    if scale not in {2, 3, 4}:
        raise ValueError("scale must be 2, 3, or 4")
    root = Path(project_dir)
    panel_dir = root / "assets" / "panels"
    panels = sorted(panel_dir.glob("*.png"), key=lambda path: path.name)
    if not panels:
        raise FileNotFoundError(f"No approved panels to upscale in {panel_dir}")
    binary = find_upscaler()
    if binary is None:
        return {
            "schema_version": "1.0",
            "status": "skipped",
            "reason": (
                "No local upscaler found. Install a Real-ESRGAN ncnn-vulkan build and either put it on PATH "
                f"or set {UPSCALER_ENV}=<path-to-executable>. Nothing was modified."
            ),
            "upscaled": [],
        }
    backup_dir = root / "assets" / "upscale-history"
    backup_dir.mkdir(parents=True, exist_ok=True)

    upscaled: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for path in panels:
        with Image.open(path) as image:
            short_side = min(image.size)
            source_size = image.size
        if only_below_short_side is not None and short_side >= only_below_short_side:
            skipped.append({"panel": path.name, "reason": f"short side {short_side} >= {only_below_short_side}"})
            continue
        result = _run_upscaler(binary, path, scale)
        if result is None:
            skipped.append({"panel": path.name, "reason": "upscaler failed; original kept"})
            continue
        shutil.copy2(path, backup_dir / f"{path.stem}-original.png")
        shutil.move(str(result), str(path))
        with Image.open(path) as image:
            new_size = image.size
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        _update_manifest_hash(root, path.stem, digest, new_size)
        upscaled.append({"panel": path.name, "from": list(source_size), "to": list(new_size)})

    report = {
        "schema_version": "1.0",
        "status": "upscaled" if upscaled else "nothing-to-do",
        "upscaler": str(binary),
        "scale": scale,
        "upscaled": upscaled,
        "skipped": skipped,
    }
    qa_dir = root / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    (qa_dir / "upscale-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def _run_upscaler(binary: Path, source: Path, scale: int) -> Path | None:
    with tempfile.TemporaryDirectory(prefix="b2c-upscale-") as tmp:
        output = Path(tmp) / f"{source.stem}-up.png"
        command = [str(binary), "-i", str(source), "-o", str(output), "-s", str(scale)]
        try:
            completed = subprocess.run(command, capture_output=True, timeout=600, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if completed.returncode != 0 or not output.is_file():
            return None
        try:
            with Image.open(output) as image:
                image.verify()
        except (OSError, SyntaxError):
            return None
        stable = source.parent / f".{source.stem}-upscaled.tmp.png"
        shutil.copy2(output, stable)
        return stable


def _update_manifest_hash(root: Path, panel_stem: str, digest: str, size: tuple[int, int]) -> None:
    manifest_path = root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        return
    if not isinstance(manifest, dict):
        return
    if not panel_stem.isdigit():
        return
    index = int(panel_stem)
    changed = False
    for asset in manifest.get("assets", []):
        if isinstance(asset, dict) and asset.get("kind") == "panel" and int(asset.get("panel_index") or 0) == index:
            asset["canonical_sha256"] = digest
            asset["width"] = size[0]
            asset["height"] = size[1]
            asset["upscaled"] = True
            changed = True
    if changed:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
