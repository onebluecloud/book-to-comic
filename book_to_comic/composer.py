from pathlib import Path
from dataclasses import dataclass, replace
import json
import os
import zipfile

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps

from .balloons import (
    DEFAULT_LETTERING_MODE,
    BalloonPlan,
    PanelBalloonPlan,
    caption_lines_for_mode,
    profile_for_style,
    render_panel_overlays,
    resolve_lettering_mode,
    strip_ballooned_lines,
)
from .models import AdaptationPackage, Panel
from .text_bible import panel_card_form_lines, panel_long_form_lines
from .fonts import find_cjk_font, load_variant


BG = (246, 241, 231)
PAPER = (255, 252, 244)
INK = (39, 38, 34)
MUTED = (106, 99, 88)
LINE = (194, 184, 166)
ACCENT = (224, 88, 51)
BLUE = (55, 119, 178)
GRID_BASE_SIZE = (1440, 2400)
LINE_START_FORBIDDEN = set("，。！？；：、）】》」』’”.,!?;:)]}%")
LINE_END_FORBIDDEN = set("（【《「『‘“([{")
CARD_ACCENT = (176, 116, 84)  # 卡片系列识别色(暖赭圆点)
CARD_THEMES = ("editorial", "gallery", "cinematic")


@dataclass(frozen=True)
class LetteringPreset:
    style_id: str
    container_kind: str
    allow_in_art_balloons: bool
    body_font_size: int
    panel_gap: int
    caption_fill: tuple[int, int, int]
    body_font_family: str = "sans"
    draw_caption_fill: bool = True
    page_bg: tuple[int, int, int] = BG
    panel_fill: tuple[int, int, int] = PAPER
    ink: tuple[int, int, int] = INK
    muted: tuple[int, int, int] = MUTED
    line: tuple[int, int, int] = LINE
    title_font_size: int = 42
    subtitle_font_size: int = 23
    panel_label_font_size: int = 30
    caption_padding_x: int = 30
    caption_padding_y: int = 22
    line_gap: int = 9
    paragraph_gap: int = 8
    margin: int = 48
    panel_padding: int = 26
    art_caption_gap: int = 22
    panel_radius: int = 18
    caption_radius: int = 10
    border_width: int = 2
    landscape_art_ratio: float = 0.46
    portrait_art_ratio: float = 0.68


@dataclass(frozen=True)
class LetteredPanelLayout:
    index: int
    panel_rect: tuple[int, int, int, int]
    art_rect: tuple[int, int, int, int]
    caption_rect: tuple[int, int, int, int]
    text_paragraphs: tuple[str, ...] = ()


@dataclass(frozen=True)
class LetteredPageLayout:
    width: int
    height: int
    preset: LetteringPreset
    panels: tuple[LetteredPanelLayout, ...]


def get_lettering_preset(style_id: str, width: int = 1080) -> LetteringPreset:
    canonical = _canonical_lettering_style(style_id)
    base_body = _scaled(width, 0.034, 36, 50)
    title_size = _scaled(width, 0.036, 36, 56)
    subtitle_size = _scaled(width, 0.018, 20, 28)
    panel_label_size = _scaled(width, 0.026, 24, 36)
    margin = _scaled(width, 0.044, 42, 64)
    padding_x = _scaled(width, 0.028, 24, 42)

    presets = {
        "editorial": dict(
            body_font_size=max(36, base_body - 8),
            panel_gap=_scaled(width, 0.020, 22, 32),
            caption_fill=(255, 252, 244),
            page_bg=(244, 239, 229),
            panel_fill=(255, 252, 244),
            line=(196, 185, 165),
            body_font_family="serif",
            draw_caption_fill=False,
            caption_radius=8,
            border_width=1,
            landscape_art_ratio=0.48,
            portrait_art_ratio=0.70,
        ),
        "ink-sketch": dict(
            body_font_size=max(35, base_body - 3),
            panel_gap=_scaled(width, 0.022, 24, 34),
            caption_fill=(249, 248, 243),
            page_bg=(241, 240, 235),
            panel_fill=(254, 253, 249),
            line=(172, 169, 160),
            caption_radius=6,
            border_width=1,
            landscape_art_ratio=0.48,
            portrait_art_ratio=0.70,
        ),
        "franco-belgian-bd": dict(
            body_font_size=base_body,
            panel_gap=_scaled(width, 0.022, 24, 36),
            caption_fill=(255, 251, 239),
            page_bg=(239, 234, 219),
            panel_fill=(255, 253, 246),
            line=(62, 59, 52),
            caption_radius=10,
            border_width=2,
            landscape_art_ratio=0.47,
            portrait_art_ratio=0.68,
        ),
        "comic-strip": dict(
            body_font_size=base_body + 1,
            panel_gap=_scaled(width, 0.018, 20, 30),
            caption_fill=(255, 255, 247),
            page_bg=(245, 238, 218),
            panel_fill=(255, 252, 241),
            line=(56, 51, 42),
            caption_radius=12,
            border_width=2,
            landscape_art_ratio=0.45,
            portrait_art_ratio=0.66,
        ),
        "manga": dict(
            body_font_size=base_body + 1,
            panel_gap=_scaled(width, 0.020, 22, 34),
            caption_fill=(255, 255, 255),
            page_bg=(232, 232, 232),
            panel_fill=(250, 250, 250),
            line=(24, 24, 24),
            caption_radius=8,
            border_width=3,
            landscape_art_ratio=0.48,
            portrait_art_ratio=0.72,
        ),
        "webtoon-manhwa": dict(
            body_font_size=base_body + 2,
            panel_gap=_scaled(width, 0.036, 38, 58),
            caption_fill=(255, 255, 255),
            page_bg=(248, 248, 248),
            panel_fill=(255, 255, 255),
            line=(218, 218, 218),
            caption_radius=18,
            border_width=1,
            landscape_art_ratio=0.50,
            portrait_art_ratio=0.78,
        ),
        "manhua": dict(
            body_font_size=base_body + 1,
            panel_gap=_scaled(width, 0.030, 32, 48),
            caption_fill=(255, 252, 247),
            page_bg=(246, 244, 239),
            panel_fill=(255, 255, 253),
            line=(205, 197, 184),
            caption_radius=14,
            border_width=1,
            landscape_art_ratio=0.50,
            portrait_art_ratio=0.74,
        ),
        "doodle": dict(
            body_font_size=max(26, base_body - 1),
            panel_gap=_scaled(width, 0.026, 28, 42),
            caption_fill=(255, 250, 225),
            page_bg=(247, 239, 215),
            panel_fill=(255, 252, 235),
            line=(137, 124, 102),
            caption_radius=16,
            border_width=2,
            landscape_art_ratio=0.46,
            portrait_art_ratio=0.68,
        ),
        "retro-halftone": dict(
            body_font_size=base_body + 3,
            panel_gap=_scaled(width, 0.020, 22, 34),
            caption_fill=(255, 238, 178),
            page_bg=(236, 219, 179),
            panel_fill=(255, 247, 218),
            line=(46, 38, 30),
            caption_radius=8,
            border_width=3,
            landscape_art_ratio=0.47,
            portrait_art_ratio=0.68,
        ),
    }
    values = presets.get(canonical, presets["editorial"])
    return LetteringPreset(
        style_id=canonical,
        container_kind="open-caption" if canonical == "editorial" else "caption-band",
        allow_in_art_balloons=False,
        title_font_size=title_size,
        subtitle_font_size=subtitle_size,
        panel_label_font_size=panel_label_size,
        caption_padding_x=padding_x,
        caption_padding_y=max(18, int(values["body_font_size"] * 0.72)),
        line_gap=max(8, int(values["body_font_size"] * 0.32)),
        paragraph_gap=max(8, int(values["body_font_size"] * 0.28)),
        margin=margin,
        panel_padding=_scaled(width, 0.026, 24, 40),
        art_caption_gap=_scaled(width, 0.018, 18, 30),
        **values,
    )


def plan_lettered_page(
    package: AdaptationPackage,
    panel_dir: str | Path | None = None,
    width: int = 1080,
    require_panels: bool = False,
    text_mode: str = "long_form",
    balloon_plan: BalloonPlan | None = None,
    lettering_mode: str = DEFAULT_LETTERING_MODE,
) -> LetteredPageLayout:
    preset = get_lettering_preset(package.style_id, width=width)
    panels_path = Path(panel_dir) if panel_dir else None
    if require_panels:
        _validate_required_panel_images(panels_path, package.storyboard)

    fonts = _fonts_for_preset(preset)
    probe = Image.new("RGB", (16, 16), preset.page_bg)
    draw = ImageDraw.Draw(probe)

    header_h = _header_height(preset)
    y = header_h + preset.panel_gap
    layouts: list[LetteredPanelLayout] = []
    panel_x0 = preset.margin
    panel_x1 = width - preset.margin
    label_h = max(48, int(preset.panel_label_font_size * 1.65))
    tall_layout = _has_portrait_panel(panels_path, package.storyboard)

    def _plan_one(panel: Panel, frame_x0: int, frame_x1: int, top: int) -> LetteredPanelLayout:
        frame_inner_x0 = frame_x0 + preset.panel_padding
        frame_inner_x1 = frame_x1 - preset.panel_padding
        frame_inner_w = frame_inner_x1 - frame_inner_x0
        art_w, art_h = _planned_art_size(panels_path, panel.index, frame_inner_w, width, preset, tall_layout=tall_layout, panel=panel)
        art_x0 = frame_inner_x0 + (frame_inner_w - art_w) // 2
        art_y0 = top + preset.panel_padding + label_h
        art_rect = (art_x0, art_y0, art_x0 + art_w, art_y0 + art_h)
        plan_panel = balloon_plan.by_index.get(panel.index) if balloon_plan else None
        paragraphs = _panel_lettering_paragraphs(panel, mode=text_mode, plan_panel=plan_panel, lettering_mode=lettering_mode)
        caption_y0 = art_rect[3] + preset.art_caption_gap
        caption_h = _caption_height(draw, paragraphs, frame_inner_x1 - frame_inner_x0, fonts["body"], preset)
        caption_rect = (frame_inner_x0, caption_y0, frame_inner_x1, caption_y0 + caption_h)
        panel_y1 = caption_rect[3] + preset.panel_padding
        return LetteredPanelLayout(
            index=panel.index,
            panel_rect=(frame_x0, top, frame_x1, panel_y1),
            art_rect=art_rect,
            caption_rect=caption_rect,
            text_paragraphs=paragraphs,
        )

    for group in _group_panels_for_layout(package.storyboard):
        if len(group) == 2:
            col_w = (panel_x1 - panel_x0 - preset.panel_gap) // 2
            left = _plan_one(group[0], panel_x0, panel_x0 + col_w, y)
            right = _plan_one(group[1], panel_x1 - col_w, panel_x1, y)
            row_y1 = max(left.panel_rect[3], right.panel_rect[3])
            left = LetteredPanelLayout(
                index=left.index,
                panel_rect=(left.panel_rect[0], left.panel_rect[1], left.panel_rect[2], row_y1),
                art_rect=left.art_rect,
                caption_rect=left.caption_rect,
                text_paragraphs=left.text_paragraphs,
            )
            right = LetteredPanelLayout(
                index=right.index,
                panel_rect=(right.panel_rect[0], right.panel_rect[1], right.panel_rect[2], row_y1),
                art_rect=right.art_rect,
                caption_rect=right.caption_rect,
                text_paragraphs=right.text_paragraphs,
            )
            layouts.extend((left, right))
            panel_y1 = row_y1
        else:
            single = _plan_one(group[0], panel_x0, panel_x1, y)
            layouts.append(single)
            panel_y1 = single.panel_rect[3]
        y = panel_y1 + preset.panel_gap + _pause_gap_after(group[-1], preset)

    height = y + preset.margin
    return LetteredPageLayout(width=width, height=height, preset=preset, panels=tuple(layouts))


def _is_half_width_panel(panel: Panel | None) -> bool:
    """Small beats and inserts may share a row; hero/large panels never do."""
    if panel is None:
        return False
    weight = str(getattr(panel, "visual_weight", "normal") or "normal").lower()
    hint = str(getattr(panel, "layout_hint", "normal") or "normal").lower()
    if weight in {"hero", "large"} or hint in {"full-width", "hero", "full", "large"}:
        return False
    return weight == "small" or hint in {"insert", "split-relation", "detail"}


def _group_panels_for_layout(storyboard: tuple[Panel, ...]) -> list[tuple[Panel, ...]]:
    groups: list[tuple[Panel, ...]] = []
    panels = list(storyboard)
    i = 0
    while i < len(panels):
        current = panels[i]
        nxt = panels[i + 1] if i + 1 < len(panels) else None
        if (
            _is_half_width_panel(current)
            and _is_half_width_panel(nxt)
            and not bool(getattr(current, "pause_after", False))
        ):
            groups.append((current, nxt))
            i += 2
        else:
            groups.append((current,))
            i += 1
    return groups


def _pause_gap_after(panel: Panel, preset: LetteringPreset) -> int:
    """Extra vertical breathing room after a pause beat (webtoon rhythm)."""
    beat = str(getattr(panel, "beat_duration", "normal") or "normal").lower()
    if bool(getattr(panel, "pause_after", False)) or beat == "pause":
        return int(preset.panel_gap * 1.8)
    return 0


def _canonical_lettering_style(style_id: str) -> str:
    aliases = {
        "advanced-flat": "webtoon-manhwa",
        "retro-comic": "retro-halftone",
        "japanese-watercolor": "doodle",
        "chinese-ink-line": "manhua",
    }
    return aliases.get(style_id, style_id)


def _scaled(width: int, ratio: float, minimum: int, maximum: int) -> int:
    return min(maximum, max(minimum, int(round(width * ratio))))


def _fonts_for_preset(preset: LetteringPreset) -> dict[str, ImageFont.FreeTypeFont]:
    if preset.body_font_family == "serif":
        regular = _font_path(("NotoSerifSC-VF.ttf", "STSONG.TTF", "simsun.ttc", "SimSun.ttf", "NotoSerifCJK-Regular.ttc", "msyh.ttc"))
        bold = _font_path(("NotoSerifSC-VF.ttf", "simhei.ttf", "simsun.ttc", "msyhbd.ttc", "NotoSerifCJK-Bold.ttc"))
    else:
        regular = _font_path(("NotoSansSC-VF.ttf", "msyh.ttc", "simhei.ttf"))
        bold = _font_path(("msyhbd.ttc", "NotoSansSC-VF.ttf", "msyh.ttc", "simhei.ttf"))
    return {
        "title": load_variant(bold, preset.title_font_size, "bold"),
        "subtitle": load_variant(regular, preset.subtitle_font_size, "regular"),
        "panel_title": load_variant(bold, preset.panel_label_font_size, "bold"),
        "body": load_variant(regular, preset.body_font_size, "regular"),
    }


def _header_height(preset: LetteringPreset) -> int:
    return max(140, preset.margin + preset.title_font_size + preset.subtitle_font_size + 52)


def _panel_lettering_paragraphs(
    panel: Panel,
    mode: str = "long_form",
    plan_panel: PanelBalloonPlan | None = None,
    lettering_mode: str = DEFAULT_LETTERING_MODE,
) -> tuple[str, ...]:
    # mode = text form (long_form/card_form); lettering_mode = balloon/hybrid/caption-only.
    lines = build_panel_overlay_text(panel, mode=mode)
    return caption_lines_for_mode(lines, plan_panel, lettering_mode)


def _caption_line_flow(
    draw: ImageDraw.ImageDraw,
    paragraphs: tuple[str, ...],
    max_width: int,
    font: ImageFont.FreeTypeFont,
    preset: LetteringPreset,
) -> tuple[list[tuple[str, int]], int]:
    """Wrap paragraphs into drawable lines and their exact vertical extent.

    Single source of truth for caption metrics: `_caption_height` reserves space
    from this flow and `_draw_lettering_paragraphs` renders it verbatim, so the
    two can never disagree again. (They used to: the estimate priced every line
    at the height of the sample string 测试 and skipped one line_gap per
    paragraph, while drawing advanced by each line's real bbox height plus a gap
    for every line — punctuation-heavy captions overflowed the box.)
    """
    lines: list[tuple[str, int]] = []
    total = 0
    for paragraph in paragraphs:
        for line in _wrap_text(draw, paragraph, max_width, font):
            line_h = _text_h(draw, line, font)
            lines.append((line, line_h))
            total += line_h + preset.line_gap
        total += preset.paragraph_gap
    return lines, total


def _caption_height(
    draw: ImageDraw.ImageDraw,
    paragraphs: tuple[str, ...],
    width: int,
    font: ImageFont.FreeTypeFont,
    preset: LetteringPreset,
) -> int:
    if not paragraphs:
        return preset.caption_padding_y * 2 + preset.body_font_size
    text_w = width - preset.caption_padding_x * 2
    _, flow_h = _caption_line_flow(draw, paragraphs, text_w, font, preset)
    bottom_safety = max(6, int(preset.body_font_size * 0.20))
    return max(int(preset.body_font_size * 3.2), flow_h + preset.caption_padding_y * 2 + bottom_safety)


def _planned_art_size(
    panel_dir: Path | None,
    index: int,
    max_width: int,
    page_width: int,
    preset: LetteringPreset,
    tall_layout: bool,
    panel: Panel | None = None,
) -> tuple[int, int]:
    image_w, image_h = _panel_image_size(panel_dir, index)
    if image_w <= 0 or image_h <= 0:
        image_w, image_h = 16, 9
    ratio = image_h / image_w
    art_ratio = preset.portrait_art_ratio if tall_layout or ratio > 1.15 else preset.landscape_art_ratio
    art_ratio *= _rhythm_art_multiplier(panel)
    max_height = max(360, int(page_width * art_ratio))
    scale = min(max_width / image_w, max_height / image_h)
    return max(1, int(round(image_w * scale))), max(1, int(round(image_h * scale)))


def _rhythm_art_multiplier(panel: Panel | None) -> float:
    if panel is None:
        return 1.0
    visual_weight = str(getattr(panel, "visual_weight", "normal") or "normal").lower()
    layout_hint = str(getattr(panel, "layout_hint", "normal") or "normal").lower()
    beat_duration = str(getattr(panel, "beat_duration", "normal") or "normal").lower()
    multiplier = 1.0
    if visual_weight in {"hero", "large"} or layout_hint in {"hero", "full", "large"}:
        multiplier += 0.28
    if beat_duration in {"slow", "held", "pause"}:
        multiplier += 0.08
    if layout_hint in {"inset", "detail"}:
        multiplier -= 0.15
    return max(0.75, min(1.45, multiplier))


def write_rhythm_layout_report(
    package: AdaptationPackage,
    layout: LetteredPageLayout,
    output_path: str | Path,
    *,
    text_mode: str,
) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    by_index = {item.index: item for item in package.storyboard}
    panels = []
    for panel_layout in layout.panels:
        panel = by_index[panel_layout.index]
        art_h = panel_layout.art_rect[3] - panel_layout.art_rect[1]
        caption_h = panel_layout.caption_rect[3] - panel_layout.caption_rect[1]
        panels.append(
            {
                "panel_index": panel.index,
                "visual_weight": str(getattr(panel, "visual_weight", "normal")),
                "layout_hint": str(getattr(panel, "layout_hint", "normal")),
                "beat_duration": str(getattr(panel, "beat_duration", "normal")),
                "visual_density": str(getattr(panel, "visual_density", "medium")),
                "text_density": str(getattr(panel, "text_density", "medium")),
                "reveal_priority": str(getattr(panel, "reveal_priority", "normal")),
                "pause_after": bool(getattr(panel, "pause_after", False)),
                "art_height": art_h,
                "caption_height": caption_h,
                "panel_rect": list(panel_layout.panel_rect),
                "art_rect": list(panel_layout.art_rect),
                "caption_rect": list(panel_layout.caption_rect),
            }
        )
    report = {
        "schema_version": "3.0",
        "text_mode": text_mode,
        "width": layout.width,
        "height": layout.height,
        "panel_count": len(panels),
        "panels": panels,
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def _panel_image_size(panel_dir: Path | None, index: int) -> tuple[int, int]:
    if not panel_dir:
        return (16, 9)
    path = _find_panel_image_path(panel_dir, index)
    if path is None:
        return (16, 9)
    with Image.open(path) as image:
        return image.size


def _has_portrait_panel(panel_dir: Path | None, panels: tuple[Panel, ...] | list[Panel]) -> bool:
    if not panel_dir:
        return False
    for panel in panels:
        width, height = _panel_image_size(panel_dir, panel.index)
        if width and height / width > 1.15:
            return True
    return False


def _draw_lettered_header(
    draw: ImageDraw.ImageDraw,
    package: AdaptationPackage,
    fonts: dict[str, ImageFont.FreeTypeFont],
    layout: LetteredPageLayout,
) -> None:
    preset = layout.preset
    x0 = preset.margin
    x1 = layout.width - preset.margin
    y0 = max(24, preset.margin // 2)
    y1 = _header_height(preset) - preset.panel_gap // 2
    draw.rounded_rectangle((x0, y0, x1, y1), radius=preset.panel_radius, fill=preset.panel_fill, outline=preset.line, width=preset.border_width)
    _draw_fitted_text(draw, package.episode_title, (x0 + preset.caption_padding_x, y0 + 18), x1 - x0 - preset.caption_padding_x * 2, fonts["title"], preset.ink)
    # light_shell / hard_core are planning vocabulary; they belong in the brief, not on the page.
    subtitle = package.book_title
    _draw_fitted_text(draw, subtitle, (x0 + preset.caption_padding_x, y0 + 78), x1 - x0 - preset.caption_padding_x * 2, fonts["subtitle"], preset.muted)


def _draw_lettered_panel(
    draw: ImageDraw.ImageDraw,
    canvas: Image.Image,
    panel: Panel,
    layout: LetteredPanelLayout,
    panel_image: Image.Image | None,
    fonts: dict[str, ImageFont.FreeTypeFont],
    preset: LetteringPreset,
    plan_panel: PanelBalloonPlan | None = None,
    lettering_mode: str = DEFAULT_LETTERING_MODE,
) -> None:
    x0, y0, x1, y1 = layout.panel_rect
    draw.rounded_rectangle(layout.panel_rect, radius=preset.panel_radius, fill=preset.panel_fill, outline=preset.line, width=preset.border_width)

    # panel.beat is a production beat label; deliverables carry the index only.
    label = f"{panel.index:02d}"
    label_w = min(x1 - x0 - preset.panel_padding * 2, _text_w(draw, label, fonts["panel_title"]) + 32)
    label_rect = (x0 + preset.panel_padding, y0 + 18, x0 + preset.panel_padding + label_w, y0 + 18 + int(preset.panel_label_font_size * 1.35))
    draw.rounded_rectangle(label_rect, radius=8, fill=_soften(preset.caption_fill, preset.panel_fill), outline=None)
    draw.text((label_rect[0] + 16, label_rect[1] + 4), label, font=fonts["panel_title"], fill=preset.ink)

    ax0, ay0, ax1, ay1 = layout.art_rect
    art_border = (max(0, ax0 - 4), max(0, ay0 - 4), min(canvas.width, ax1 + 4), min(canvas.height, ay1 + 4))
    draw.rounded_rectangle(art_border, radius=7, fill=(34, 33, 30))
    if panel_image:
        pasted_rect = _paste_panel_image(canvas, panel_image, layout.art_rect)
        if plan_panel is not None:
            render_panel_overlays(canvas, pasted_rect, plan_panel, font_family=preset.body_font_family, ink=preset.ink, lettering_mode=lettering_mode, profile=profile_for_style(preset.style_id))
    else:
        _draw_placeholder_art(draw, layout.art_rect, panel, _fonts())

    if preset.draw_caption_fill:
        draw.rounded_rectangle(
            layout.caption_rect,
            radius=preset.caption_radius,
            fill=preset.caption_fill,
            outline=preset.line,
            width=preset.border_width,
        )
    else:
        cx0, cy0, cx1, _ = layout.caption_rect
        draw.line((cx0, cy0, cx1, cy0), fill=_soften(preset.line, preset.panel_fill), width=1)
    _draw_lettering_paragraphs(draw, layout.text_paragraphs, layout.caption_rect, fonts["body"], preset)


def _shift_panel_layout(layout: LetteredPanelLayout, dy: int) -> LetteredPanelLayout:
    return LetteredPanelLayout(
        index=layout.index,
        panel_rect=_shift_rect(layout.panel_rect, dy),
        art_rect=_shift_rect(layout.art_rect, dy),
        caption_rect=_shift_rect(layout.caption_rect, dy),
        text_paragraphs=layout.text_paragraphs,
    )


def _shift_rect(rect: tuple[int, int, int, int], dy: int) -> tuple[int, int, int, int]:
    return (rect[0], rect[1] + dy, rect[2], rect[3] + dy)


def _draw_lettering_paragraphs(
    draw: ImageDraw.ImageDraw,
    paragraphs: tuple[str, ...],
    rect: tuple[int, int, int, int],
    font: ImageFont.FreeTypeFont,
    preset: LetteringPreset,
) -> None:
    x0, y0, x1, _ = rect
    x = x0 + preset.caption_padding_x
    y = y0 + preset.caption_padding_y
    max_width = x1 - x0 - preset.caption_padding_x * 2
    # Per-paragraph flow is additive, so rendering paragraph-by-paragraph lands on
    # exactly the total that _caption_height reserved.
    for paragraph in paragraphs:
        para_lines, _ = _caption_line_flow(draw, (paragraph,), max_width, font, preset)
        for line, line_h in para_lines:
            draw.text((x, y), line, font=font, fill=preset.ink)
            y += line_h + preset.line_gap
        y += preset.paragraph_gap


def _draw_fitted_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    max_width: int,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
) -> None:
    if _text_w(draw, text, font) <= max_width:
        draw.text(xy, text, font=font, fill=fill)
        return
    clipped = text
    while clipped and _text_w(draw, clipped + "...", font) > max_width:
        clipped = clipped[:-1]
    draw.text(xy, clipped + "...", font=font, fill=fill)


def _soften(color: tuple[int, int, int], against: tuple[int, int, int]) -> tuple[int, int, int]:
    return tuple(int(channel * 0.72 + base * 0.28) for channel, base in zip(color, against))


def build_panel_overlay_text(panel: Panel, mode: str = "long") -> list[str]:
    if mode in {"card", "card_form"}:
        lines = panel_card_form_lines(panel)
    elif mode in {"long", "long_form"}:
        lines = panel_long_form_lines(panel)
    else:
        raise ValueError("mode must be long_form or card_form")
    seen: set[str] = set()
    result: list[str] = []
    for line in lines:
        cleaned = line.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def compose_long_image(
    package: AdaptationPackage,
    output_path: str | Path,
    panel_dir: str | Path | None = None,
    width: int = 1080,
    require_panels: bool = False,
    text_mode: str = "long_form",
    rhythm_report_path: str | Path | None = None,
    balloon_plan: BalloonPlan | None = None,
    lettering_mode: str = DEFAULT_LETTERING_MODE,
) -> Path:
    lettering_mode = resolve_lettering_mode(lettering_mode)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    layout = plan_lettered_page(package, panel_dir=panel_dir, width=width, require_panels=require_panels, text_mode=text_mode, balloon_plan=balloon_plan, lettering_mode=lettering_mode)
    panels_path = Path(panel_dir) if panel_dir else None
    fonts = _fonts_for_preset(layout.preset)

    image = Image.new("RGB", (layout.width, layout.height), layout.preset.page_bg)
    draw = ImageDraw.Draw(image)
    _draw_lettered_header(draw, package, fonts, layout)

    by_index = {panel.index: panel for panel in package.storyboard}
    for panel_layout in layout.panels:
        panel = by_index[panel_layout.index]
        panel_image = _load_panel_image(panels_path, panel.index) if panels_path else None
        plan_panel = balloon_plan.by_index.get(panel.index) if balloon_plan else None
        _draw_lettered_panel(draw, image, panel, panel_layout, panel_image, fonts, layout.preset, plan_panel=plan_panel, lettering_mode=lettering_mode)

    image.save(output, "PNG")
    if rhythm_report_path:
        write_rhythm_layout_report(package, layout, rhythm_report_path, text_mode=text_mode)
    return output


def extract_panels_from_grid(source_grid_path: str | Path, output_dir: str | Path) -> list[Path]:
    source = Path(source_grid_path)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    with Image.open(source) as image:
        rgb = image.convert("RGB")
        paths: list[Path] = []
        for index, rect in enumerate(_sample_art_rects(rgb.size), start=1):
            panel = rgb.crop(rect)
            path = destination / f"{index:02d}.png"
            panel.save(path, "PNG")
            paths.append(path)
    return paths


def validate_panel_images(
    panel_dir: str | Path,
    panels: tuple[Panel, ...] | list[Panel],
    min_width: int = 512,
    min_height: int = 256,
) -> list[dict[str, object]]:
    panels_path = Path(panel_dir)
    _validate_required_panel_images(panels_path, panels)

    report: list[dict[str, object]] = []
    for panel in panels:
        path = _find_panel_image_path(panels_path, panel.index)
        if path is None:
            raise FileNotFoundError(f"Missing required panel image in {panels_path}: {panel.index:02d}.png")
        with Image.open(path) as image:
            width, height = image.size
            if image.format != "PNG":
                raise ValueError(f"{path.name} must be a PNG image, got {image.format or 'unknown'}")
            if width < min_width or height < min_height:
                raise ValueError(
                    f"{path.name} is too small: {width}x{height}; expected at least {min_width}x{min_height}"
                )
            report.append({"index": panel.index, "name": path.name, "path": str(path), "width": width, "height": height})
    return report


def compose_subtitled_panel_images(
    package: AdaptationPackage,
    panel_dir: str | Path,
    output_dir: str | Path,
    width: int = 1080,
    balloon_plan: BalloonPlan | None = None,
    lettering_mode: str = DEFAULT_LETTERING_MODE,
) -> list[Path]:
    lettering_mode = resolve_lettering_mode(lettering_mode)
    panels_path = Path(panel_dir)
    _validate_required_panel_images(panels_path, package.storyboard)

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    preset = get_lettering_preset(package.style_id, width=width)
    fonts = _fonts_for_preset(preset)

    paths: list[Path] = []
    for panel in package.storyboard:
        single_package = replace(package, storyboard=(panel,))
        page_layout = plan_lettered_page(single_package, panels_path, width=width, require_panels=True, balloon_plan=balloon_plan, lettering_mode=lettering_mode)
        source_layout = page_layout.panels[0]
        panel_h = source_layout.panel_rect[3] - source_layout.panel_rect[1]
        image = Image.new("RGB", (width, panel_h + preset.margin * 2), preset.page_bg)
        draw = ImageDraw.Draw(image)
        panel_image = _load_panel_image(panels_path, panel.index)
        shifted = _shift_panel_layout(source_layout, dy=preset.margin - source_layout.panel_rect[1])
        plan_panel = balloon_plan.by_index.get(panel.index) if balloon_plan else None
        _draw_lettered_panel(draw, image, panel, shifted, panel_image, fonts, preset, plan_panel=plan_panel, lettering_mode=lettering_mode)
        path = destination / f"{panel.index:02d}.png"
        image.save(path, "PNG")
        paths.append(path)
    return paths


# ============ 卡片背景主题系统(按书气质选) ============
# editorial=现代杂志白卡(通用) / gallery=画廊装裱(文学) / cinematic=电影感深底(奇观)。
# 主题由 host 按书气质写进 project.json 的 card_theme;缺省 editorial(白卡最通用不会难看)。
# 三套共用同一排版引擎:中文避头尾禁则 + 避孤字回补 + 正文两端对齐 + 居中平衡断行 + 自适应缩字号。

_CARD_PUNCT_HEAD = set("，。、；：！？）］｝》」』”’·.…%")
_CARD_PUNCT_ALL = _CARD_PUNCT_HEAD | set("（［｛《「『“‘")


def normalize_card_theme(card_theme: str | None) -> str:
    theme = (card_theme or "").strip().lower()
    return theme if theme in CARD_THEMES else "editorial"


def _card_fonts(width: int) -> dict[str, ImageFont.FreeTypeFont]:
    serif = str(find_cjk_font(extra_candidates=(
        "NotoSerifSC-VF.ttf", "STSONG.TTF", "NotoSerifCJK-Regular.ttc", "simsun.ttc", "msyh.ttc",
    )))
    return {
        "title": ImageFont.truetype(serif, _scaled(width, 0.031, 30, 36)),
        "meta": ImageFont.truetype(serif, _scaled(width, 0.025, 25, 30)),
        "body": ImageFont.truetype(serif, _scaled(width, 0.036, 34, 42)),
    }


def _card_real_len(s: str) -> int:
    return sum(1 for c in s if c not in _CARD_PUNCT_ALL)


def _card_wrap(draw, text, font, max_w):
    lines: list[str] = []
    cur = ""
    for ch in text:
        if not cur:
            cur = ch
            continue
        if draw.textlength(cur + ch, font=font) <= max_w:
            cur += ch
        elif ch in _CARD_PUNCT_HEAD:
            cur += ch  # 标点不落行首(避头尾)
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    while len(lines) >= 2 and _card_real_len(lines[-1]) <= 1 and len(lines[-2]) >= 3:
        lines[-1] = lines[-2][-1] + lines[-1]  # 避孤字:末行单字从上行回补
        lines[-2] = lines[-2][:-1]
    return lines


def _card_wrap_balanced(draw, text, font, max_w):
    lines = _card_wrap(draw, text, font, max_w)
    if len(lines) == 2:
        full = lines[0] + lines[1]
        best = None
        for k in range(2, len(full) - 1):
            a, b = full[:k], full[k:]
            if b[0] in _CARD_PUNCT_HEAD:
                continue
            wa = draw.textlength(a, font=font)
            wb = draw.textlength(b, font=font)
            if wa <= max_w and wb <= max_w:
                diff = abs(wa - wb)
                if best is None or diff < best[0]:
                    best = (diff, a, b)
        if best:
            lines = [best[1], best[2]]
    return lines


def _card_measure(draw, paras, font, w, line_gap, para_gap, balanced):
    wrapper = _card_wrap_balanced if balanced else _card_wrap
    total = 0
    for p in paras:
        for _ln in wrapper(draw, p, font, w):
            total += font.size + line_gap
        total += para_gap
    return total


def _card_text(draw, paras, x, y, w, base_font, fill, line_gap, para_gap, mode, center_x=None, max_h=None):
    balanced = mode == "center"
    font = base_font
    if max_h is not None and paras:
        for delta in range(0, 16, 2):
            font = base_font.font_variant(size=max(24, base_font.size - delta))
            if _card_measure(draw, paras, font, w, line_gap, para_gap, balanced) <= max_h:
                break
    wrapper = _card_wrap_balanced if balanced else _card_wrap
    # Flatten to (line, is_last_of_paragraph) then hard-clip to max_h. Shrinking
    # bottoms out at 24px; anything still too tall used to paint past the card
    # edge onto the page background — clip and mark the cut with an ellipsis.
    flat: list[tuple[str, bool]] = []
    for p in paras:
        lines = wrapper(draw, p, font, w)
        for i, ln in enumerate(lines):
            flat.append((ln, i == len(lines) - 1))
    if max_h is not None and flat:
        budget = max_h
        kept = 0
        for ln, para_end in flat:
            cost = font.size + line_gap + (para_gap if para_end else 0)
            if budget - cost < 0 and kept > 0:
                break
            budget -= cost
            kept += 1
        if kept < len(flat):
            clipped_line = flat[kept - 1][0]
            while clipped_line and draw.textlength(clipped_line + "…", font=font) > w:
                clipped_line = clipped_line[:-1]
            flat = flat[: kept - 1] + [(clipped_line + "…", True)]
    for ln, para_end in flat:
        if mode == "center":
            lw = draw.textlength(ln, font=font)
            draw.text((center_x - lw / 2, y), ln, font=font, fill=fill)
        elif mode == "justify" and not para_end and len(ln) > 1:
            cw = sum(draw.textlength(c, font=font) for c in ln)
            gap = (w - cw) / (len(ln) - 1)
            cx = x
            for c in ln:
                draw.text((cx, y), c, font=font, fill=fill)
                cx += draw.textlength(c, font=font) + gap
        else:
            draw.text((x, y), ln, font=font, fill=fill)
        y += font.size + line_gap
        if para_end:
            y += para_gap
    return y


def _card_shadow(size, box, radius, blur, alpha, offset):
    s = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(s)
    bx = (box[0] + offset[0], box[1] + offset[1], box[2] + offset[0], box[3] + offset[1])
    d.rounded_rectangle(bx, radius=radius, fill=(0, 0, 0, alpha))
    return s.filter(ImageFilter.GaussianBlur(blur))


def _card_round(img, radius):
    img = img.convert("RGBA")
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.size[0], img.size[1]), radius=radius, fill=255)
    img.putalpha(mask)
    return img


def _card_vgrad(size, top, bottom):
    img = Image.new("RGB", size)
    d = ImageDraw.Draw(img)
    w, h = size
    for y in range(h):
        t = y / (h - 1)
        d.line((0, y, w, y), fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return img


def _card_scrim(size, height, color=(8, 10, 16)):
    w, h = size
    ov = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    for i in range(height):
        y = h - height + i
        a = int(240 * (i / height) ** 1.5)
        d.line((0, y, w, y), fill=color + (a,))
    return ov


def _card_header(draw, fonts, title, idx, total, x, right, y, title_fill, meta_fill, line_fill):
    draw.ellipse((x, y + 8, x + 22, y + 30), fill=CARD_ACCENT)
    draw.text((x + 40, y), title, font=fonts["title"], fill=title_fill)
    meta = f"{idx:02d}/{total:02d}"
    mw = draw.textlength(meta, font=fonts["meta"])
    draw.text((right - mw, y + 6), meta, font=fonts["meta"], fill=meta_fill)
    draw.line((x, y + 58, right, y + 58), fill=line_fill, width=2)


def _render_editorial(panel_img, fonts, title, idx, total, paras, w, h):
    base = Image.new("RGB", (w, h), (246, 243, 237))
    m, r, pad = _scaled(w, 0.037, 36, 44), 34, _scaled(w, 0.052, 50, 60)
    card = (m, m, w - m, h - m)
    base = Image.alpha_composite(base.convert("RGBA"), _card_shadow((w, h), card, r, 32, 55, (0, 20))).convert("RGB")
    d = ImageDraw.Draw(base)
    d.rounded_rectangle(card, radius=r, fill=(255, 255, 255))
    hx, hy = m + pad, m + pad
    _card_header(d, fonts, title, idx, total, hx, w - m - pad, hy, (58, 53, 48), (152, 144, 133), (228, 222, 212))
    ax0, ay0, ax1 = m + pad, hy + 98, w - m - pad
    fit = ImageOps.contain(panel_img.convert("RGB"), (ax1 - ax0, int(h * 0.55)))
    fx = ax0 + ((ax1 - ax0) - fit.width) // 2
    base.paste(_card_round(fit, 18), (fx, ay0), _card_round(fit, 18))
    d = ImageDraw.Draw(base)
    ty = ay0 + fit.height + 46
    _card_text(d, paras, m + pad, ty, w - 2 * (m + pad), fonts["body"], (46, 42, 38), 22, 30, "justify", max_h=(h - m - pad) - ty)
    return base, (fx, ay0, fx + fit.width, ay0 + fit.height)


def _render_gallery(panel_img, fonts, title, idx, total, paras, w, h):
    base = Image.new("RGB", (w, h), (235, 232, 226))
    d = ImageDraw.Draw(base)
    outer = _scaled(w, 0.059, 58, 68)
    _card_header(d, fonts, title, idx, total, outer, w - outer, 60, (70, 64, 56), (150, 142, 130), (216, 210, 199))
    fit = ImageOps.contain(panel_img.convert("RGB"), (int(w * 0.685), int(h * 0.514)))
    mat = _scaled(w, 0.054, 52, 62)
    ix = (w - fit.width) // 2
    mx0, my0 = ix - mat, int(h * 0.147)
    mx1, my1 = ix + fit.width + mat, my0 + fit.height + 2 * mat
    base = Image.alpha_composite(base.convert("RGBA"), _card_shadow((w, h), (mx0, my0, mx1, my1), 4, 24, 48, (0, 16))).convert("RGB")
    d = ImageDraw.Draw(base)
    d.rectangle((mx0, my0, mx1, my1), fill=(250, 248, 244))
    d.rectangle((mx0 + 16, my0 + 16, mx1 - 16, my1 - 16), outline=(212, 205, 192), width=2)
    base.paste(fit, (ix, my0 + mat))
    d = ImageDraw.Draw(base)
    ty = my1 + 56
    _card_text(d, paras, 0, ty, w - 240, fonts["body"], (72, 66, 58), 22, 28, "center", center_x=w // 2, max_h=(h - 56) - ty)
    return base, (ix, my0 + mat, ix + fit.width, my0 + mat + fit.height)


def _render_cinematic(panel_img, fonts, title, idx, total, paras, w, h):
    base = _card_vgrad((w, h), (15, 19, 27), (32, 39, 52)).convert("RGBA")
    fit = ImageOps.contain(panel_img.convert("RGB"), (w - 96, int(h * 0.722)))
    fx, fy = (w - fit.width) // 2, 150
    base.alpha_composite(_card_round(fit, 10), (fx, fy))
    base = Image.alpha_composite(base, _card_scrim((w, h), int(h * 0.333))).convert("RGB")
    d = ImageDraw.Draw(base)
    d.text((64, 66), title, font=fonts["title"], fill=(232, 234, 240))
    d.line((64, 112, 64 + d.textlength(title, font=fonts["title"]), 112), fill=(198, 168, 110), width=2)
    meta = f"{idx:02d}/{total:02d}"
    mw = d.textlength(meta, font=fonts["meta"])
    d.text((w - 64 - mw, 72), meta, font=fonts["meta"], fill=(150, 158, 170))
    ty = h - 292
    _card_text(d, paras, 64, ty, w - 128, fonts["body"], (238, 240, 244), 22, 26, "justify", max_h=(h - 56) - ty)
    return base, (fx, fy, fx + fit.width, fy + fit.height)


_CARD_RENDERERS = {
    "editorial": _render_editorial,
    "gallery": _render_gallery,
    "cinematic": _render_cinematic,
}


def compose_carousel_card_images(
    package: AdaptationPackage,
    panel_dir: str | Path,
    output_dir: str | Path,
    width: int = 1080,
    height: int = 1440,
    balloon_plan: BalloonPlan | None = None,
    lettering_mode: str = DEFAULT_LETTERING_MODE,
    card_theme: str | None = None,
) -> list[Path]:
    lettering_mode = resolve_lettering_mode(lettering_mode)
    panels_path = Path(panel_dir)
    _validate_required_panel_images(panels_path, package.storyboard)
    if width <= 0 or height <= 0:
        raise ValueError("Card width and height must be positive integers")

    renderer = _CARD_RENDERERS[normalize_card_theme(card_theme)]
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    fonts = _card_fonts(width)
    title = package.episode_title.strip() or f"《{package.book_title}》"
    total = len(package.storyboard)

    paths: list[Path] = []
    for panel in package.storyboard:
        panel_image = _load_panel_image(panels_path, panel.index)
        if panel_image is None:
            raise FileNotFoundError(f"Missing required panel image in {panels_path}: {panel.index:02d}.png")
        plan_panel = balloon_plan.by_index.get(panel.index) if balloon_plan else None
        # 卡片文案用完整 long_form(与长图同源),不用压缩的 card_form。
        paras = _panel_lettering_paragraphs(panel, mode="long_form", plan_panel=plan_panel, lettering_mode=lettering_mode)
        image, art_rect = renderer(panel_image, fonts, title, panel.index, total, paras, width, height)
        panel_image.close()
        if plan_panel is not None:
            render_panel_overlays(image, art_rect, plan_panel, font_family="sans", ink=(32, 30, 27), lettering_mode=lettering_mode, profile=profile_for_style(package.style_id))
        path = destination / f"{panel.index:02d}.png"
        image.save(path, "PNG")
        paths.append(path)
    return paths


def compose_xiaohongshu_card_images(
    package: AdaptationPackage,
    panel_dir: str | Path,
    output_dir: str | Path,
    width: int = 1080,
    height: int = 1440,
    card_theme: str | None = None,
) -> list[Path]:
    return compose_carousel_card_images(package, panel_dir, output_dir, width=width, height=height, card_theme=card_theme)


def render_cover_overlay(
    base_panel: str | Path,
    output_path: str | Path,
    *,
    title: str,
    hook_line: str,
    # Reader-facing line under the rule; pipeline slogans (书籍 -> 漫画) are not copy.
    subtitle: str = "",
    layout: str = "big-title-on-panel",
    palette: str = "editorial-dark",
    width: int = 1080,
    height: int = 1440,
) -> Path:
    """Render a publish cover from approved panel art plus Pillow lettering."""
    source_path = Path(base_panel)
    if not source_path.exists():
        raise FileNotFoundError(f"Cover base panel is missing: {source_path}")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    colors = _cover_palette(palette)
    fonts = _cover_fonts(width)
    image = Image.new("RGB", (width, height), colors["bg"])
    draw = ImageDraw.Draw(image)
    with Image.open(source_path) as source:
        if layout == "input-to-output":
            art_rect = (70, 250, width - 70, 1030)
        else:
            art_rect = (0, 0, width, height)
        art = ImageOps.fit(source.convert("RGB"), (art_rect[2] - art_rect[0], art_rect[3] - art_rect[1]), method=Image.Resampling.LANCZOS, centering=(0.5, 0.42))
        image.paste(art, (art_rect[0], art_rect[1]))
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)

    def _scrim(base: tuple[int, int, int, int], region: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        """Darkening scrim scaled to the art it covers: a fixed 230-alpha wash
        crushed already-dark painterly covers (deco) into featureless black.
        Sample the region and back off the alpha when the art is already dark."""
        crop = image.crop(region).resize((1, 1), Image.Resampling.BILINEAR).convert("RGB")
        r, g, b = crop.getpixel((0, 0))
        luma = 0.299 * r + 0.587 * g + 0.114 * b
        base_a = base[3]
        # bright art (luma>=140) keeps full scrim; dark art (luma<=40) gets ~40% of it
        factor = 0.4 + 0.6 * min(1.0, max(0.0, (luma - 40) / 100))
        return (base[0], base[1], base[2], int(base_a * factor))

    if layout == "input-to-output":
        odraw.rectangle((0, 0, width, 230), fill=colors["top_overlay"])
        odraw.rectangle((0, 1040, width, height), fill=_scrim(colors["bottom_overlay"], (0, 1040, width, height)))
        text_box = (72, 56, width - 72, 225)
        hook_box = (72, 1092, width - 72, height - 150)
    else:
        odraw.rectangle((0, 0, width, height), fill=_scrim(colors["full_overlay"], (0, 0, width, height)))
        odraw.rectangle((0, height - 470, width, height), fill=_scrim(colors["bottom_overlay"], (0, height - 470, width, height)))
        text_box = (72, height - 410, width - 72, height - 222)
        hook_box = (72, 84, width - 72, 300)
    image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(image)
    _draw_cover_wrapped(draw, hook_line, hook_box, fonts["hook"], colors["accent"], max_lines=3)
    _draw_cover_wrapped(draw, title, text_box, fonts["title"], colors["ink"], max_lines=2)
    if subtitle.strip():
        draw.text((72, height - 124), subtitle, font=fonts["subtitle"], fill=colors["muted"])
        draw.line((72, height - 150, width - 72, height - 150), fill=colors["rule"], width=2)
    image.save(output, "PNG")
    return output


def _cover_palette(name: str) -> dict[str, tuple[int, int, int] | tuple[int, int, int, int]]:
    if name == "editorial-warm":
        return {
            "bg": (244, 238, 226),
            "ink": (248, 240, 222),
            "muted": (218, 196, 158),
            "accent": (255, 210, 92),
            "rule": (216, 174, 83),
            "full_overlay": (18, 15, 12, 96),
            "top_overlay": (18, 15, 12, 230),
            "bottom_overlay": (18, 15, 12, 230),
        }
    return {
        "bg": (21, 19, 17),
        "ink": (248, 242, 230),
        "muted": (198, 184, 158),
        "accent": (235, 178, 66),
        "rule": (154, 118, 55),
        "full_overlay": (0, 0, 0, 116),
        "top_overlay": (0, 0, 0, 230),
        "bottom_overlay": (0, 0, 0, 235),
    }


def _cover_fonts(width: int) -> dict[str, ImageFont.FreeTypeFont]:
    regular = _font_path(("NotoSerifSC-VF.ttf", "STSONG.TTF", "simsun.ttc", "SimSun.ttf", "msyh.ttc"))
    bold = _font_path(("NotoSerifSC-VF.ttf", "msyhbd.ttc", "simhei.ttf", "simsun.ttc", "msyh.ttc"))
    return {
        "hook": load_variant(bold, _scaled(width, 0.072, 62, 84), "bold"),
        "title": load_variant(bold, _scaled(width, 0.054, 48, 64), "bold"),
        "subtitle": load_variant(regular, _scaled(width, 0.030, 30, 38), "regular"),
    }


def _draw_cover_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    rect: tuple[int, int, int, int],
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
    *,
    max_lines: int,
) -> None:
    x0, y0, x1, y1 = rect
    max_width = x1 - x0
    size = font.size
    lines: list[str] = []
    active_font = font
    while size >= 28:
        active_font = font.font_variant(size=size)
        lines = _wrap_text(draw, text, max_width, active_font)
        line_h = _text_h(draw, "测试", active_font) + max(8, int(size * 0.18))
        if len(lines) <= max_lines and len(lines) * line_h <= y1 - y0:
            break
        size -= 4
    y = y0
    line_h = _text_h(draw, "测试", active_font) + max(8, int(active_font.size * 0.18))
    for line in lines[:max_lines]:
        draw.text((x0, y), line, font=active_font, fill=fill)
        y += line_h


def create_contact_sheet(
    panel_dir: str | Path,
    panels: tuple[Panel, ...] | list[Panel],
    output_path: str | Path,
    columns: int = 2,
    thumb_size: tuple[int, int] = (640, 360),
) -> Path:
    panels_path = Path(panel_dir)
    _validate_required_panel_images(panels_path, panels)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    rows = (len(panels) + columns - 1) // columns
    margin = 44
    gap = 28
    label_h = 34
    width = margin * 2 + columns * thumb_size[0] + (columns - 1) * gap
    height = margin * 2 + rows * (thumb_size[1] + label_h) + (rows - 1) * gap
    sheet = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(sheet)
    fonts = _fonts()

    for item, panel in enumerate(panels):
        row, col = divmod(item, columns)
        x = margin + col * (thumb_size[0] + gap)
        y = margin + row * (thumb_size[1] + label_h + gap)
        path = _find_panel_image_path(panels_path, panel.index)
        if path is None:
            raise FileNotFoundError(f"Missing required panel image in {panels_path}: {panel.index:02d}.png")
        with Image.open(path) as source:
            thumb = ImageOps.contain(source.convert("RGB"), thumb_size)
        draw.rounded_rectangle((x, y, x + thumb_size[0], y + thumb_size[1]), radius=16, fill=PAPER, outline=LINE, width=3)
        px = x + (thumb_size[0] - thumb.width) // 2
        py = y + (thumb_size[1] - thumb.height) // 2
        sheet.paste(thumb, (px, py))
        draw.text((x + 4, y + thumb_size[1] + 8), f"{panel.index:02d}. {panel.beat}", font=fonts["small"], fill=INK)

    sheet.save(output, "PNG")
    return output


def build_review_package(
    package: AdaptationPackage,
    panel_dir: str | Path,
    output_dir: str | Path,
    zip_path: str | Path | None = None,
    width: int = 1080,
    stem: str | None = None,
) -> dict[str, object]:
    panels_path = Path(panel_dir)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    file_stem = stem or _slug(package.book_title)

    report = validate_panel_images(panels_path, package.storyboard)
    raw_contact = create_contact_sheet(
        panels_path,
        package.storyboard,
        destination / f"{file_stem}-raw-contact-sheet.png",
    )
    subtitled_dir = destination / f"{file_stem}-subtitled-panels"
    subtitled_panels = compose_subtitled_panel_images(package, panels_path, subtitled_dir, width=width)
    subtitled_contact = create_contact_sheet(
        subtitled_dir,
        package.storyboard,
        destination / f"{file_stem}-subtitled-contact-sheet.png",
    )
    long_image = compose_long_image(
        package,
        destination / f"{file_stem}-review-long.png",
        panel_dir=panels_path,
        width=width,
        require_panels=True,
    )
    manifest = destination / f"{file_stem}-manifest.json"
    manifest_data = {
        "book_title": package.book_title,
        "episode_title": package.episode_title,
        "panel_dir": str(panels_path),
        "raw_contact_sheet": str(raw_contact),
        "subtitled_contact_sheet": str(subtitled_contact),
        "long_image": str(long_image),
        "subtitled_panels": [str(path) for path in subtitled_panels],
        "panels": report,
    }
    manifest.write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    archive = Path(zip_path) if zip_path else destination / f"{file_stem}-review-package.zip"
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(manifest, manifest.name)
        zf.write(raw_contact, raw_contact.name)
        zf.write(subtitled_contact, subtitled_contact.name)
        zf.write(long_image, long_image.name)
        for panel in package.storyboard:
            raw_path = _find_panel_image_path(panels_path, panel.index)
            if raw_path is None:
                raise FileNotFoundError(f"Missing required panel image in {panels_path}: {panel.index:02d}.png")
            zf.write(raw_path, f"raw-panels/{panel.index:02d}.png")
        for path in subtitled_panels:
            zf.write(path, f"subtitled-panels/{path.name}")

    return {
        "raw_contact_sheet": raw_contact,
        "subtitled_contact_sheet": subtitled_contact,
        "long_image": long_image,
        "manifest": manifest,
        "zip": archive,
        "subtitled_panels": subtitled_panels,
    }


def _fonts() -> dict[str, ImageFont.FreeTypeFont]:
    regular = _font_path(("NotoSansSC-VF.ttf", "msyh.ttc", "simhei.ttf"))
    bold = _font_path(("msyhbd.ttc", "NotoSansSC-VF.ttf", "simhei.ttf"))
    return {
        "title": load_variant(bold, 42, "bold"),
        "subtitle": load_variant(regular, 23, "regular"),
        "panel_title": load_variant(bold, 30, "bold"),
        "visual": load_variant(regular, 24, "regular"),
        "overlay": load_variant(bold, 28, "bold"),
        "small": load_variant(regular, 22, "regular"),
    }


def _font_path(candidates: tuple[str, ...]) -> Path:
    return find_cjk_font(extra_candidates=candidates)


def _draw_header(
    draw: ImageDraw.ImageDraw,
    package: AdaptationPackage,
    fonts: dict[str, ImageFont.FreeTypeFont],
    width: int,
    margin: int,
) -> None:
    draw.rounded_rectangle((margin, 32, width - margin, 146), radius=26, fill=PAPER, outline=LINE, width=3)
    draw.text((margin + 30, 50), package.episode_title, font=fonts["title"], fill=INK)
    subtitle = f"{package.book_title} · {package.light_shell} x {package.hard_core}"
    draw.text((margin + 32, 108), subtitle, font=fonts["subtitle"], fill=MUTED)


def _draw_panel(
    draw: ImageDraw.ImageDraw,
    canvas: Image.Image,
    rect: tuple[int, int, int, int],
    panel: Panel,
    panel_image: Image.Image | None,
    fonts: dict[str, ImageFont.FreeTypeFont],
    art_height: int = 282,
) -> None:
    x0, y0, x1, y1 = rect
    draw.rounded_rectangle(rect, radius=20, fill=PAPER, outline=LINE, width=3)
    draw.rounded_rectangle((x0 + 22, y0 + 18, x0 + 190, y0 + 62), radius=15, fill=(238, 229, 211))
    draw.text((x0 + 38, y0 + 23), f"{panel.index}. {panel.beat}", font=fonts["panel_title"], fill=INK)

    art_rect = (x0 + 26, y0 + 78, x1 - 26, y0 + 78 + art_height)
    text_rect = (x0 + 26, art_rect[3] + 18, x1 - 26, y1 - 24)
    if panel_image:
        _paste_panel_image(canvas, panel_image, art_rect)
    else:
        _draw_placeholder_art(draw, art_rect, panel, fonts)

    draw.rounded_rectangle(text_rect, radius=16, fill=(255, 255, 255), outline=(224, 215, 198), width=2)
    overlay = build_panel_overlay_text(panel)
    _multiline(draw, "\n".join(overlay), (text_rect[0] + 20, text_rect[1] + 16), text_rect[2] - text_rect[0] - 40, fonts["overlay"], INK, 8)


def _draw_placeholder_art(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    panel: Panel,
    fonts: dict[str, ImageFont.FreeTypeFont],
) -> None:
    x0, y0, x1, y1 = rect
    draw.rounded_rectangle(rect, radius=18, fill=(250, 247, 239), outline=(220, 210, 190), width=2)
    draw.rectangle((x0, y0, x1, y0 + 12), fill=ACCENT)
    draw.rectangle((x0, y1 - 12, x1, y1), fill=BLUE)
    draw.ellipse((x0 + 40, y0 + 48, x0 + 128, y0 + 136), fill=(245, 201, 158), outline=INK, width=3)
    draw.rounded_rectangle((x0 + 56, y0 + 128, x0 + 116, y0 + 218), radius=18, fill=ACCENT, outline=INK, width=3)
    draw.ellipse((x1 - 142, y0 + 58, x1 - 54, y0 + 146), fill=(245, 201, 158), outline=BLUE, width=3)
    draw.rounded_rectangle((x1 - 160, y0 + 138, x1 - 36, y0 + 224), radius=22, fill=BLUE, outline=(27, 76, 128), width=3)
    _multiline(draw, panel.visual, (x0 + 180, y0 + 56), x1 - x0 - 360, fonts["visual"], MUTED, 8)


def _paste_panel_image(canvas: Image.Image, panel_image: Image.Image, rect: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = rect
    framed = ImageOps.contain(panel_image.convert("RGB"), (x1 - x0, y1 - y0))
    px = x0 + (x1 - x0 - framed.width) // 2
    py = y0 + (y1 - y0 - framed.height) // 2
    canvas.paste(framed, (px, py))
    return (px, py, px + framed.width, py + framed.height)


def _load_panel_image(panel_dir: Path | None, index: int) -> Image.Image | None:
    if not panel_dir or not panel_dir.exists():
        return None
    path = _find_panel_image_path(panel_dir, index)
    if path:
        return Image.open(path)
    return None


def _art_height_for_panels(
    panel_dir: Path | None,
    panels: tuple[Panel, ...] | list[Panel],
    width: int,
    margin: int,
) -> int:
    default_art_h = 282
    if not panel_dir or not panel_dir.exists():
        return default_art_h

    ratios: list[float] = []
    for panel in panels:
        path = _find_panel_image_path(panel_dir, panel.index)
        if path is None:
            continue
        with Image.open(path) as image:
            if image.width:
                ratios.append(image.height / image.width)
    if not ratios:
        return default_art_h

    representative_ratio = sorted(ratios)[len(ratios) // 2]
    tallest_ratio = max(ratios)
    layout_ratio = tallest_ratio if tallest_ratio > 1.05 else representative_ratio
    if layout_ratio <= 0.9:
        return default_art_h

    art_w = width - margin * 2 - 52
    return min(820, max(520, int(art_w * layout_ratio)))


def _validate_required_panel_images(panel_dir: Path | None, panels: list[Panel]) -> None:
    if not panel_dir:
        raise FileNotFoundError("Panel directory is required when require_panels=True")
    if not panel_dir.exists():
        raise FileNotFoundError(f"Panel directory does not exist: {panel_dir}")

    missing = [f"{panel.index:02d}.png" for panel in panels if not _find_panel_image_path(panel_dir, panel.index)]
    if missing:
        joined = ", ".join(missing)
        raise FileNotFoundError(f"Missing required panel image(s) in {panel_dir}: {joined}")


def _find_panel_image_path(panel_dir: Path, index: int) -> Path | None:
    names = (
        f"{index}.png",
        f"{index:02d}.png",
        f"panel-{index}.png",
        f"panel_{index}.png",
        f"第{index}格.png",
    )
    for name in names:
        path = panel_dir / name
        if path.exists():
            return path
    return None


def _slug(text: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "-" for char in text).strip("-")
    return "-".join(part for part in slug.split("-") if part) or "comic"


def _sample_art_rects(size: tuple[int, int]) -> list[tuple[int, int, int, int]]:
    width, height = size
    sx = width / GRID_BASE_SIZE[0]
    sy = height / GRID_BASE_SIZE[1]
    margin = 50
    top = 158
    gutter = 24
    panel_w = (GRID_BASE_SIZE[0] - margin * 2 - gutter) // 2
    panel_h = 532
    rects: list[tuple[int, int, int, int]] = []
    for row in range(4):
        for col in range(2):
            x0 = margin + col * (panel_w + gutter)
            y0 = top + row * (panel_h + gutter)
            x1 = x0 + panel_w
            y1 = y0 + panel_h
            art = (x0 + 26, y0 + 66, x1 - 26, y1 - 156)
            rects.append(tuple(round(value) for value in (art[0] * sx, art[1] * sy, art[2] * sx, art[3] * sy)))
    return rects


def _multiline(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    max_width: int,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
    line_gap: int,
) -> None:
    x, y = xy
    for paragraph in text.splitlines():
        for line in _wrap_text(draw, paragraph, max_width, font):
            draw.text((x, y), line, font=font, fill=fill)
            y += _text_h(draw, line, font) + line_gap
        y += line_gap


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, max_width: int, font: ImageFont.FreeTypeFont) -> list[str]:
    if not text:
        return [""]
    lines: list[str] = []
    current = ""
    for char in text:
        trial = current + char
        if _text_w(draw, trial, font) <= max_width or not current:
            current = trial
        else:
            if char in LINE_START_FORBIDDEN:
                current += char
                continue
            line = current
            current = char
            if len(line) > 1 and line[-1] in LINE_END_FORBIDDEN:
                current = line[-1] + current
                line = line[:-1]
            lines.append(line)
    if current:
        lines.append(current)
    return lines


def _text_w(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _text_h(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[3] - box[1]
