from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from .composer import _font_path


PAPER = (250, 246, 236)
INK = (39, 37, 33)
LINE = (70, 66, 58)
GOLD = (198, 146, 54)
BLUE = (66, 118, 168)
RED = (190, 82, 62)
GREEN = (88, 138, 96)
SKIN = (229, 190, 150)


def render_vector_episode(
    episode_path: str | Path,
    output_dir: str | Path,
    width: int = 1080,
    height: int = 720,
) -> list[Path]:
    episode_file = Path(episode_path)
    episode = json.loads(episode_file.read_text(encoding="utf-8"))
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    panels = _episode_panels(episode)
    if not panels:
        raise ValueError(f"No panels found in {episode_file}")

    paths: list[Path] = []
    for index, panel in enumerate(panels, start=1):
        image = _draw_panel(panel, index=index, width=width, height=height)
        _stamp_draft_watermark(image)
        path = destination / f"{index:02d}.png"
        image.save(path, "PNG")
        paths.append(path)
    return paths


def _stamp_draft_watermark(image: Image.Image) -> None:
    """Mark vector fallback art as DRAFT so it can never pass for finished art.

    The vector path is an explicit draft/diagnostic fallback (see SKILL.md);
    the watermark makes that status visible on the pixels themselves instead of
    relying on everyone reading the docs (P0-1: bypass paths degrade loudly).
    """
    draw = ImageDraw.Draw(image)
    label = "DRAFT / 草稿"
    try:
        font = ImageFont.truetype(
            _font_path(("NotoSansSC-VF.ttf", "msyh.ttc", "simhei.ttf")),
            max(18, image.height // 18),
        )
    except (OSError, ValueError):
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), label, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = image.width - text_w - 16
    y = image.height - text_h - 14
    draw.rectangle((x - 8, y - 6, x + text_w + 8, y + text_h + 8), fill=(255, 255, 255))
    draw.text((x, y), label, fill=(190, 82, 62), font=font)


def _episode_panels(episode: dict[str, Any]) -> list[dict[str, Any]]:
    scenes = episode.get("scenes")
    if isinstance(scenes, list) and scenes:
        panels: list[dict[str, Any]] = []
        for scene in scenes:
            if not isinstance(scene, dict):
                continue
            scene_panels = scene.get("panels")
            if isinstance(scene_panels, list):
                panels.extend(panel for panel in scene_panels if isinstance(panel, dict))
        return panels
    storyboard = episode.get("storyboard")
    if isinstance(storyboard, list):
        return [panel for panel in storyboard if isinstance(panel, dict)]
    panels = episode.get("panels")
    if isinstance(panels, list):
        return [panel for panel in panels if isinstance(panel, dict)]
    return []


def _draw_panel(panel: dict[str, Any], index: int, width: int, height: int) -> Image.Image:
    palette = _palette(index)
    image = Image.new("RGB", (width, height), palette["sky"])
    draw = ImageDraw.Draw(image)
    fonts = _fonts()

    _draw_scene(draw, width, height, palette, index)
    _draw_camera_frame(draw, width, height)
    _draw_characters(draw, width, height, palette, index, panel)
    _draw_props(draw, width, height, palette, index)
    _draw_motion_and_mood(draw, width, height, palette, index, panel)
    _draw_panel_index(draw, index, fonts)
    return image


def _palette(index: int) -> dict[str, tuple[int, int, int]]:
    palettes = [
        {"sky": (240, 235, 222), "floor": (218, 205, 180), "accent": GOLD, "shadow": (122, 91, 61)},
        {"sky": (226, 235, 237), "floor": (202, 215, 211), "accent": BLUE, "shadow": (60, 86, 110)},
        {"sky": (239, 229, 224), "floor": (222, 197, 184), "accent": RED, "shadow": (112, 68, 62)},
        {"sky": (229, 236, 222), "floor": (207, 220, 197), "accent": GREEN, "shadow": (67, 96, 68)},
    ]
    return palettes[(index - 1) % len(palettes)]


def _draw_scene(
    draw: ImageDraw.ImageDraw,
    width: int,
    height: int,
    palette: dict[str, tuple[int, int, int]],
    index: int,
) -> None:
    horizon = int(height * 0.58)
    draw.rectangle((0, horizon, width, height), fill=palette["floor"])
    draw.line((0, horizon, width, horizon), fill=LINE, width=4)

    if index % 3 == 1:
        for x in range(90, width, 190):
            draw.rectangle((x, 120, x + 62, horizon - 18), fill=(118, 89, 58), outline=LINE, width=3)
            for y in range(140, horizon - 30, 46):
                draw.line((x + 8, y, x + 54, y), fill=(230, 204, 139), width=5)
    elif index % 3 == 2:
        draw.rounded_rectangle((90, 105, width - 90, 300), radius=22, fill=(247, 244, 233), outline=LINE, width=4)
        for x in range(130, width - 120, 90):
            draw.line((x, 130, x + 40, 275), fill=palette["accent"], width=5)
    else:
        for x in range(60, width, 150):
            draw.polygon((x, horizon, x + 54, 170, x + 108, horizon), fill=(222, 218, 205), outline=LINE)
            draw.rectangle((x + 25, horizon - 92, x + 83, horizon), fill=(190, 160, 116), outline=LINE, width=3)


def _draw_camera_frame(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    margin = 28
    draw.rounded_rectangle((margin, margin, width - margin, height - margin), radius=22, outline=LINE, width=5)
    draw.rounded_rectangle((margin + 10, margin + 10, width - margin - 10, height - margin - 10), radius=16, outline=(255, 253, 246), width=2)


def _draw_characters(
    draw: ImageDraw.ImageDraw,
    width: int,
    height: int,
    palette: dict[str, tuple[int, int, int]],
    index: int,
    panel: dict[str, Any],
) -> None:
    names = panel.get("characters_present") or ["主角", "引路人"]
    count = min(3, max(1, len(names)))
    base_y = int(height * 0.74)
    spacing = width // (count + 1)
    for pos in range(count):
        x = spacing * (pos + 1)
        scale = 1.0 if pos == 0 else 0.88
        color = (palette["accent"] if pos == 0 else BLUE if pos == 1 else GREEN)
        _draw_person(draw, x, base_y, color, scale=scale, turned=(index + pos) % 2 == 0)


def _draw_person(
    draw: ImageDraw.ImageDraw,
    cx: int,
    foot_y: int,
    clothing: tuple[int, int, int],
    scale: float = 1.0,
    turned: bool = False,
) -> None:
    head_r = int(42 * scale)
    torso_w = int(86 * scale)
    torso_h = int(130 * scale)
    head_y = foot_y - torso_h - head_r * 2 - int(16 * scale)

    draw.ellipse((cx - head_r, head_y, cx + head_r, head_y + head_r * 2), fill=SKIN, outline=INK, width=4)
    hair_top = head_y + int(8 * scale)
    draw.arc((cx - head_r, hair_top - head_r, cx + head_r, hair_top + head_r), 190, 350, fill=INK, width=9)
    eye_y = head_y + int(48 * scale)
    eye_dx = int(16 * scale)
    draw.ellipse((cx - eye_dx - 4, eye_y, cx - eye_dx + 4, eye_y + 6), fill=INK)
    draw.ellipse((cx + eye_dx - 4, eye_y, cx + eye_dx + 4, eye_y + 6), fill=INK)
    mouth_y = head_y + int(76 * scale)
    if turned:
        draw.arc((cx - 14, mouth_y - 10, cx + 22, mouth_y + 14), 15, 150, fill=INK, width=3)
    else:
        draw.arc((cx - 20, mouth_y - 8, cx + 20, mouth_y + 14), 20, 160, fill=INK, width=3)

    torso = (cx - torso_w // 2, head_y + head_r * 2 + 12, cx + torso_w // 2, head_y + head_r * 2 + 12 + torso_h)
    draw.rounded_rectangle(torso, radius=int(24 * scale), fill=clothing, outline=INK, width=4)
    shoulder_y = torso[1] + int(26 * scale)
    arm_span = int(88 * scale)
    if turned:
        draw.line((torso[0], shoulder_y, torso[0] - arm_span, shoulder_y + 48), fill=INK, width=int(10 * scale))
        draw.line((torso[2], shoulder_y, torso[2] + arm_span // 2, shoulder_y + 18), fill=INK, width=int(10 * scale))
    else:
        draw.line((torso[0], shoulder_y, torso[0] - arm_span // 2, shoulder_y + 36), fill=INK, width=int(10 * scale))
        draw.line((torso[2], shoulder_y, torso[2] + arm_span, shoulder_y - 8), fill=INK, width=int(10 * scale))
    leg_y = torso[3]
    draw.line((cx - int(22 * scale), leg_y, cx - int(50 * scale), foot_y), fill=INK, width=int(12 * scale))
    draw.line((cx + int(22 * scale), leg_y, cx + int(50 * scale), foot_y), fill=INK, width=int(12 * scale))
    draw.line((cx - int(72 * scale), foot_y, cx - int(36 * scale), foot_y), fill=INK, width=int(10 * scale))
    draw.line((cx + int(36 * scale), foot_y, cx + int(72 * scale), foot_y), fill=INK, width=int(10 * scale))


def _draw_props(
    draw: ImageDraw.ImageDraw,
    width: int,
    height: int,
    palette: dict[str, tuple[int, int, int]],
    index: int,
) -> None:
    table_y = int(height * 0.68)
    draw.rounded_rectangle((width // 2 - 150, table_y, width // 2 + 150, table_y + 30), radius=10, fill=(118, 84, 52), outline=INK, width=3)
    draw.line((width // 2 - 120, table_y + 30, width // 2 - 150, table_y + 100), fill=INK, width=5)
    draw.line((width // 2 + 120, table_y + 30, width // 2 + 150, table_y + 100), fill=INK, width=5)
    if index % 2:
        for i in range(4):
            x = width // 2 - 108 + i * 48
            draw.polygon((x, table_y - 4, x + 40, table_y - 20, x + 80, table_y - 4), fill=(235, 222, 186), outline=INK)
    else:
        door = (width - 230, 135, width - 96, table_y + 5)
        draw.rounded_rectangle(door, radius=14, fill=(245, 226, 159), outline=palette["shadow"], width=6)
        draw.ellipse((door[2] - 34, (door[1] + door[3]) // 2, door[2] - 20, (door[1] + door[3]) // 2 + 14), fill=palette["shadow"])
        for r in range(18, 74, 18):
            draw.arc((door[0] - r, door[1] - r, door[2] + r, door[3] + r), 300, 60, fill=(245, 213, 104), width=3)


def _draw_motion_and_mood(
    draw: ImageDraw.ImageDraw,
    width: int,
    height: int,
    palette: dict[str, tuple[int, int, int]],
    index: int,
    panel: dict[str, Any],
) -> None:
    action = str(panel.get("action") or panel.get("visual") or "")
    for i in range(5):
        x = 100 + i * 72
        y = 76 + (i % 3) * 40
        draw.arc((x, y, x + 58, y + 36), 200, 340, fill=palette["accent"], width=4)
    if "门" in action or index % 4 == 0:
        draw.line((width - 300, 120, width - 190, 70), fill=GOLD, width=8)
        draw.line((width - 285, 190, width - 160, 188), fill=GOLD, width=6)
    if "空" in action or index % 5 == 0:
        draw.ellipse((78, 90, 170, 182), outline=palette["shadow"], width=5)
        draw.ellipse((101, 113, 147, 159), fill=PAPER, outline=None)


def _draw_panel_index(draw: ImageDraw.ImageDraw, index: int, fonts: dict[str, ImageFont.FreeTypeFont]) -> None:
    label = f"{index:02d}"
    draw.rounded_rectangle((48, 48, 126, 108), radius=12, fill=(255, 252, 241), outline=LINE, width=3)
    draw.text((64, 56), label, font=fonts["index"], fill=INK)


def _fonts() -> dict[str, ImageFont.FreeTypeFont]:
    regular = _font_path(("NotoSerifSC-VF.ttf", "STSONG.TTF", "simsun.ttc", "SimSun.ttf", "msyh.ttc"))
    return {
        "index": ImageFont.truetype(str(regular), 34),
    }
