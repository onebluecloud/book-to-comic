"""Cross-panel consistency sheets for host visual QA.

After all panels are approved, these deterministic sheets let the host (or a
human) catch drift in one glance instead of paging through panels one by one:

- one sheet per character: every panel that character appears in, with the
  approved character reference as the first tile for baseline comparison;
- one sheet per scene: every panel of that scene side by side, so background,
  light direction, and prop continuity mismatches pop out.

The sheets are review artifacts (``review/consistency/``); they never enter the
final delivery package.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from .fonts import find_cjk_font, load_variant
from .project_layout import load_episode

TILE_WIDTH = 460
TILE_COLUMNS = 3
LABEL_HEIGHT = 44
SHEET_MARGIN = 28
TILE_GAP = 18
SHEET_BG = (240, 237, 230)
LABEL_INK = (52, 46, 38)
REFERENCE_TINT = (196, 146, 58)


def build_consistency_sheets(project_dir: str | Path) -> dict[str, Any]:
    root = Path(project_dir)
    panel_dir = root / "assets" / "panels"
    panel_paths = sorted(panel_dir.glob("*.png"), key=lambda path: path.name)
    if not panel_paths:
        raise FileNotFoundError(
            f"No approved panels found in {panel_dir}. Approve panels before building consistency sheets."
        )
    episode = load_episode(root)
    scenes = episode.get("scenes") if isinstance(episode.get("scenes"), list) else []

    by_character: dict[str, list[int]] = {}
    by_scene: dict[str, list[int]] = {}
    scene_locations: dict[str, str] = {}
    index = 0
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        scene_key = str(scene.get("scene_id") or f"S{len(by_scene) + 1}")
        scene_locations[scene_key] = str(scene.get("location") or "")
        panels = scene.get("panels") if isinstance(scene.get("panels"), list) else []
        for panel in panels:
            index += 1
            if index > len(panel_paths):
                break
            by_scene.setdefault(scene_key, []).append(index)
            names = panel.get("characters_present") if isinstance(panel, dict) else None
            if isinstance(names, list):
                for name in names:
                    cleaned = str(name).strip()
                    if cleaned:
                        by_character.setdefault(cleaned, []).append(index)

    output_dir = root / "review" / "consistency"
    output_dir.mkdir(parents=True, exist_ok=True)
    font = load_variant(find_cjk_font("regular"), 26, "regular")
    reference = root / "assets" / "references" / "character-reference.png"

    sheets: list[dict[str, Any]] = []
    for position, (name, indexes) in enumerate(sorted(by_character.items()), start=1):
        filename = f"character-{position:02d}.png"
        tiles: list[tuple[str, Path, bool]] = []
        if reference.is_file():
            tiles.append(("定妆参考", reference, True))
        tiles.extend((f"P{i:02d}", panel_dir / f"{i:02d}.png", False) for i in indexes)
        _render_sheet(output_dir / filename, f"角色一致性：{name}", tiles, font)
        sheets.append({"kind": "character", "subject": name, "file": f"review/consistency/{filename}", "panels": indexes})

    for scene_key, indexes in by_scene.items():
        if len(indexes) < 2:
            continue
        filename = f"scene-{_safe_name(scene_key)}.png"
        location = scene_locations.get(scene_key, "")
        title = f"场景一致性：{scene_key}" + (f"（{location}）" if location else "")
        tiles = [(f"P{i:02d}", panel_dir / f"{i:02d}.png", False) for i in indexes]
        _render_sheet(output_dir / filename, title, tiles, font)
        sheets.append({"kind": "scene", "subject": scene_key, "file": f"review/consistency/{filename}", "panels": indexes})

    summary = {
        "schema_version": "1.0",
        "panel_count": len(panel_paths),
        "character_sheets": sum(1 for sheet in sheets if sheet["kind"] == "character"),
        "scene_sheets": sum(1 for sheet in sheets if sheet["kind"] == "scene"),
        "sheets": sheets,
        "notes": (
            "宿主必须逐张查看：角色表对照第一格定妆参考，检查脸型/发型/服装/体型漂移；"
            "场景表检查同一场景的空间结构、光源方向、道具连续性是否一致。"
            "发现漂移只重生漂移格，不整套重画。"
        ),
    }
    if not by_character:
        summary["warnings"] = [
            "episode panels 缺少 characters_present 字段，无法生成角色一致性表；只生成了场景表。"
        ]
    (output_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def _render_sheet(
    output: Path,
    title: str,
    tiles: list[tuple[str, Path, bool]],
    font: ImageFont.FreeTypeFont,
) -> None:
    loaded: list[tuple[str, Image.Image, bool]] = []
    for label, path, is_reference in tiles:
        if not path.is_file():
            continue
        with Image.open(path) as source:
            image = source.convert("RGB")
            scale = TILE_WIDTH / image.width
            image = image.resize((TILE_WIDTH, max(1, int(image.height * scale))), Image.LANCZOS)
            loaded.append((label, image, is_reference))
    if not loaded:
        return
    columns = min(TILE_COLUMNS, len(loaded))
    rows: list[list[tuple[str, Image.Image, bool]]] = [
        loaded[i : i + columns] for i in range(0, len(loaded), columns)
    ]
    row_heights = [max(tile[1].height for tile in row) + LABEL_HEIGHT for row in rows]
    width = SHEET_MARGIN * 2 + columns * TILE_WIDTH + (columns - 1) * TILE_GAP
    header_h = 72
    height = header_h + SHEET_MARGIN * 2 + sum(row_heights) + (len(rows) - 1) * TILE_GAP
    sheet = Image.new("RGB", (width, height), SHEET_BG)
    draw = ImageDraw.Draw(sheet)
    draw.text((SHEET_MARGIN, 24), title, font=font, fill=LABEL_INK)
    draw.line((SHEET_MARGIN, header_h - 8, width - SHEET_MARGIN, header_h - 8), fill=(190, 180, 162), width=2)
    y = header_h + SHEET_MARGIN
    for row, row_h in zip(rows, row_heights):
        x = SHEET_MARGIN
        for label, image, is_reference in row:
            outline = REFERENCE_TINT if is_reference else (120, 112, 100)
            draw.rectangle((x - 2, y + LABEL_HEIGHT - 2, x + TILE_WIDTH + 2, y + LABEL_HEIGHT + image.height + 2), outline=outline, width=3 if is_reference else 1)
            draw.text((x + 2, y + 6), label, font=font, fill=REFERENCE_TINT if is_reference else LABEL_INK)
            sheet.paste(image, (x, y + LABEL_HEIGHT))
            x += TILE_WIDTH + TILE_GAP
        y += row_h + TILE_GAP
    for _, image, _ in loaded:
        image.close()
    sheet.save(output, "PNG")


def _safe_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "-_" else "-" for char in value.strip())
    return cleaned.strip("-") or "scene"
