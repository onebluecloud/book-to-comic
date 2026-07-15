from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from .project_layout import load_episode, resolve_episode_id, save_episode, validate_episode_id
from .story_gate import flatten_episode_panels


SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
DEFAULT_MIN_WIDTH = 900
DEFAULT_MIN_HEIGHT = 600
DEFAULT_MIN_FILE_BYTES = 100_000


def import_host_image_panels(
    project_dir: str | Path,
    image_dir: str | Path,
    episode_id: str | None = None,
    min_width: int = DEFAULT_MIN_WIDTH,
    min_height: int = DEFAULT_MIN_HEIGHT,
    min_file_bytes: int = DEFAULT_MIN_FILE_BYTES,
) -> dict[str, object]:
    """LEGACY bulk handoff for the codex-exec worker path (generate-final).

    Accepts a directory of worker-produced files positionally and registers
    them as approved without per-panel host QA — acceptable only because the
    legacy worker flow is explicitly non-default and its output is draft-tier.
    The OFFICIAL manual-image path is the inbox (inbox-prepare/inbox-import):
    strict filenames, candidates, per-panel approve. Do not point new flows
    here.
    """
    root = Path(project_dir)
    source_dir = Path(image_dir)
    if not source_dir.exists():
        raise FileNotFoundError(f"Host image directory does not exist: {source_dir}")
    if min_width <= 0 or min_height <= 0 or min_file_bytes < 0:
        raise ValueError("Minimum width/height must be positive and min file bytes cannot be negative")

    episode = load_episode(root)
    episode_id = validate_episode_id(resolve_episode_id(episode, episode_id))
    panels = flatten_episode_panels(episode)
    if not isinstance(panels, list) or not panels:
        raise ValueError(f"Official episode has no panels: {root / 'story' / 'episode-001.json'}")

    sources = _ordered_image_paths(source_dir)
    if len(sources) != len(panels):
        raise ValueError(
            f"Host image count mismatch for {episode_id}: expected {len(panels)} panel image(s), "
            f"found {len(sources)} in {source_dir}. Put only final accepted panel images in this directory."
        )

    quality_report = [
        _validate_host_image(path, min_width=min_width, min_height=min_height, min_file_bytes=min_file_bytes)
        for path in sources
    ]

    panels_dir = root / "assets" / "panels"
    original_dir = root / "assets" / "host-image-sources" / episode_id
    panels_dir.mkdir(parents=True, exist_ok=True)
    original_dir.mkdir(parents=True, exist_ok=True)

    assets: list[dict[str, object]] = []
    for index, (source, panel, report) in enumerate(zip(sources, panels, quality_report), start=1):
        original_path = original_dir / f"{index:02d}{source.suffix.lower()}"
        if source.resolve() != original_path.resolve():
            shutil.copy2(source, original_path)

        output_path = panels_dir / f"{index:02d}.png"
        with Image.open(source) as image:
            normalized = ImageOps.exif_transpose(image).convert("RGB")
            normalized.save(output_path, "PNG", optimize=True)

        relative_output = output_path.relative_to(root).as_posix()
        relative_original = original_path.relative_to(root).as_posix()
        if isinstance(panel, dict):
            panel["asset_path"] = relative_output
            panel["status"] = "rendered"
            panel["image_backend"] = "host-image"

        assets.append(
            {
                "panel_id": panel.get("panel_id", f"P{index:02d}") if isinstance(panel, dict) else f"P{index:02d}",
                "backend": "host-image",
                "quality_tier": "imported",
                "path": relative_output,
                "source_path": relative_original,
                "prompt": panel.get("image_prompt", "") if isinstance(panel, dict) else "",
                "status": "rendered",
                "redo_count": 0,
                "quality": report,
            }
        )

    save_episode(root, episode)
    _write_json(
        root / "assets" / "panel_assets.json",
        {
            "schema_version": "1.0",
            "backend": "host-image",
            "quality_tier": "imported",
            "assets": assets,
        },
    )
    qa = _host_image_qa_report(episode_id, assets, quality_report)
    _write_json(root / "qa" / "host-image-report.json", qa)

    # Register imported panels as approved assets in manifest.json so that
    # validate-project-assets / compose-project (which read manifest.json, not
    # panel_assets.json) accept host-imported / inbox artwork.
    _sync_panel_manifest(root, len(assets))

    return {
        "project_dir": str(root),
        "episode_id": episode_id,
        "backend": "host-image",
        "quality_tier": "imported",
        "panel_count": len(assets),
        "panels_dir": str(panels_dir),
        "source_dir": str(original_dir),
        "assets": assets,
    }


def _ordered_image_paths(image_dir: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in image_dir.iterdir()
            if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES
        ),
        key=_natural_key,
    )


def _natural_key(path: Path) -> tuple[object, ...]:
    parts = re.split(r"(\d+)", path.stem)
    key: list[object] = []
    for part in parts:
        key.append(int(part) if part.isdigit() else part.lower())
    key.append(path.suffix.lower())
    return tuple(key)


def _validate_host_image(path: Path, min_width: int, min_height: int, min_file_bytes: int) -> dict[str, object]:
    if path.stat().st_size < min_file_bytes:
        raise ValueError(
            f"Host image is too small to accept as high-quality artwork: {path.name} "
            f"({path.stat().st_size} bytes < {min_file_bytes})"
        )
    with Image.open(path) as image:
        width, height = image.size
        if width < min_width or height < min_height:
            raise ValueError(
                f"Host image is below the minimum panel size: {path.name} "
                f"({width}x{height} < {min_width}x{min_height})"
            )
        colors = image.convert("RGB").getcolors(maxcolors=1_000_000)
        color_count = len(colors) if colors is not None else ">1000000"
    return {
        "source_name": path.name,
        "width": width,
        "height": height,
        "bytes": path.stat().st_size,
        "format": path.suffix.lower().lstrip("."),
        "color_count": color_count,
        "passed": True,
    }


def _host_image_qa_report(
    episode_id: str,
    assets: list[dict[str, object]],
    quality_report: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "status": "host-image-imported",
        "episode_id": episode_id,
        "backend": "host-image",
        "quality_tier": "imported",
        "panel_count": len(assets),
        "warnings": [],
        "checks": {
            "host_images_imported": True,
            "all_images_pass_min_size": True,
            "post_production_lettering": False,
            "not_vector_fallback": True,
        },
        "quality_report": quality_report,
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sync_panel_manifest(root: Path, panel_count: int) -> None:
    """Register imported panels as approved entries in manifest.json.

    compose-project gates read manifest.json (the materialize pipeline's source
    of truth), so host-image / inbox imports must land there too. Non-panel
    assets (e.g. a character reference) are preserved; existing panel entries are
    replaced by the freshly imported set.
    """
    manifest_path = root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            manifest = {}
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        manifest = {}

    kept = [
        asset
        for asset in manifest.get("assets", [])
        if isinstance(asset, dict) and asset.get("kind") != "panel"
    ]
    panels_dir = root / "assets" / "panels"
    for index in range(1, panel_count + 1):
        canonical = panels_dir / f"{index:02d}.png"
        digest = hashlib.sha256(canonical.read_bytes()).hexdigest()
        kept.append(
            {
                "asset_id": f"panel-{index:02d}",
                "version": 1,
                "kind": "panel",
                "status": "approved",
                "panel_index": index,
                "canonical_path": f"assets/panels/{index:02d}.png",
                "canonical_sha256": digest,
                "source_mode": "host-image-import",
            }
        )
    manifest["schema_version"] = manifest.get("schema_version", "2.0")
    manifest["assets"] = kept
    _write_json(manifest_path, manifest)


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
