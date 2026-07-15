from pathlib import Path
import os
import textwrap

from PIL import Image, ImageDraw, ImageFont

from .fonts import find_cjk_font, load_variant


PAGE_SIZE = (1440, 2400)
BG = (246, 241, 231)
INK = (39, 38, 34)
MUTED = (100, 93, 82)
PANEL_BG = (255, 252, 244)
PANEL_LINE = (194, 184, 166)
FAST = (224, 88, 51)
SLOW = (55, 119, 178)
SLOW_DARK = (27, 76, 128)
SKIN = (245, 201, 158)
CREAM_SHIRT = (255, 244, 222)
DARK_TROUSERS = (50, 50, 54)
BLACK_SHOE = (24, 24, 22)
WARM = (238, 171, 86)
GREEN = (88, 151, 101)


PANELS = (
    {
        "beat": "钩子",
        "caption": "你以为做主的是「你」？其实决策驾驶台上常驻这俩——平时是左边那个在开车。",
    },
    {
        "beat": "快脑登场",
        "caption": "快脑（系统1）：秒出答案，管你95%的日常。快，但爱抄近路。",
        "dialogue": "2+2=4！红灯停！这人在笑=开心！",
    },
    {
        "beat": "慢脑登场",
        "caption": "慢脑（系统2）：能算对、会深想，但是个懒鬼。",
        "dialogue": "17×24？啊……让我缓缓……",
    },
    {
        "beat": "关键设定",
        "caption": "快脑抢答，慢脑懒得查，随手盖章放行。于是——",
    },
    {
        "beat": "锚定·上",
        "caption": "划线价一出现，快脑立刻把「便宜了多少」当成重点。",
        "dialogue": "才299？！便宜700！买它！",
    },
    {
        "beat": "锚定·下",
        "caption": "没人问：它本身到底值多少？",
        "dialogue": "快脑说划算……那就划算吧。",
    },
    {
        "beat": "点破",
        "caption": "那¥999是商家丢给你快脑的「锚」。你以为在算计，其实被一个数字带跑。",
    },
    {
        "beat": "收口",
        "caption": "下次看到划线价，叫醒慢脑问一句：抛开原价，它本身值多少？",
        "hook": "你最近被哪个「原价」套路过？",
    },
)


def render_thinking_fast_and_slow_comic(output_path: str | Path, blank_text: bool = False) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    image = Image.new("RGB", PAGE_SIZE, BG)
    draw = ImageDraw.Draw(image)
    fonts = _fonts()

    _draw_page_header(draw, fonts)
    panels = _panel_rects()
    for index, rect in enumerate(panels, start=1):
        _draw_panel(draw, rect, index, PANELS[index - 1], fonts, blank_text=blank_text)

    image.save(output, "PNG")
    return output


def _fonts() -> dict[str, ImageFont.FreeTypeFont]:
    regular_path = _font_path(("NotoSansSC-VF.ttf", "msyh.ttc", "simhei.ttf"))
    bold_path = _font_path(("msyhbd.ttc", "NotoSansSC-VF.ttf", "simhei.ttf"))
    return {
        "title": load_variant(bold_path, 48, "bold"),
        "subtitle": load_variant(regular_path, 25, "regular"),
        "beat": load_variant(bold_path, 27, "bold"),
        "caption": load_variant(regular_path, 25, "regular"),
        "dialogue": load_variant(bold_path, 25, "bold"),
        "small": load_variant(regular_path, 21, "regular"),
    }


def _font_path(candidates: tuple[str, ...]) -> Path:
    return find_cjk_font(extra_candidates=candidates)


def _draw_page_header(draw: ImageDraw.ImageDraw, fonts: dict[str, ImageFont.FreeTypeFont]) -> None:
    draw.rounded_rectangle((52, 34, 1388, 132), radius=28, fill=(252, 248, 239), outline=PANEL_LINE, width=3)
    draw.text((82, 54), "《思考，快与慢》EP1：快脑抢答，慢脑盖章", font=fonts["title"], fill=INK)
    draw.text((84, 107), "系统1 / 系统2 × 锚定效应 · vector 样板漫画", font=fonts["subtitle"], fill=MUTED)


def _panel_rects() -> list[tuple[int, int, int, int]]:
    page_w, _ = PAGE_SIZE
    margin = 50
    top = 158
    gutter = 24
    panel_w = (page_w - margin * 2 - gutter) // 2
    panel_h = 532
    rects = []
    for row in range(4):
        for col in range(2):
            x0 = margin + col * (panel_w + gutter)
            y0 = top + row * (panel_h + gutter)
            rects.append((x0, y0, x0 + panel_w, y0 + panel_h))
    return rects


def _draw_panel(
    draw: ImageDraw.ImageDraw,
    rect: tuple[int, int, int, int],
    index: int,
    data: dict[str, str],
    fonts: dict[str, ImageFont.FreeTypeFont],
    blank_text: bool,
) -> None:
    x0, y0, x1, y1 = rect
    draw.rounded_rectangle(rect, radius=18, fill=PANEL_BG, outline=PANEL_LINE, width=3)
    draw.rounded_rectangle((x0 + 16, y0 + 14, x0 + 122, y0 + 54), radius=14, fill=(238, 229, 211))
    draw.text((x0 + 30, y0 + 18), f"{index}. {data['beat']}", font=fonts["beat"], fill=INK)

    art = (x0 + 26, y0 + 66, x1 - 26, y1 - 156)
    caption = (x0 + 22, y1 - 142, x1 - 22, y1 - 22)
    scene_drawer = (
        _scene_decision_dashboard,
        _scene_fast,
        _scene_slow,
        _scene_stamp,
        _scene_anchor_price,
        _scene_checkout,
        _scene_merchant_anchor,
        _scene_wake_slow,
    )[index - 1]
    scene_drawer(draw, art, fonts, blank_text)

    if "dialogue" in data:
        _speech(draw, art, data["dialogue"], fonts, side="right" if index in (2, 5) else "left", blank_text=blank_text)

    draw.rounded_rectangle(caption, radius=14, fill=(250, 246, 236), outline=(224, 215, 198), width=2)
    if not blank_text:
        caption_text = data["caption"]
        if "hook" in data:
            caption_text += "\n评论钩子：" + data["hook"]
        _multiline(draw, caption_text, (caption[0] + 14, caption[1] + 12), caption[2] - caption[0] - 28, fonts["caption"], INK, line_gap=6)


def _scene_decision_dashboard(draw: ImageDraw.ImageDraw, art: tuple[int, int, int, int], fonts: dict[str, ImageFont.FreeTypeFont], blank_text: bool) -> None:
    x0, y0, x1, y1 = art
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    draw.rounded_rectangle((x0 + 42, y0 + 34, x1 - 42, y1 - 18), radius=24, fill=(239, 243, 238), outline=PANEL_LINE, width=4)
    draw.rounded_rectangle((cx - 156, y0 + 52, cx + 156, y0 + 136), radius=16, fill=(222, 238, 241), outline=(156, 177, 180), width=3)
    draw.rounded_rectangle((x0 + 92, y0 + 190, x1 - 92, y0 + 278), radius=18, fill=(229, 218, 199), outline=(173, 158, 136), width=4)
    draw.ellipse((cx - 210, y0 + 204, cx - 144, y0 + 270), outline=INK, width=6)
    draw.line((cx - 177, y0 + 237, cx - 177, y0 + 205), fill=INK, width=5)
    for bx in (cx - 54, cx - 20, cx + 14, cx + 48):
        draw.ellipse((bx, y0 + 216, bx + 18, y0 + 234), fill=WARM, outline=INK, width=2)
    draw.rounded_rectangle((cx + 92, y0 + 182, cx + 220, y0 + 274), radius=20, fill=(216, 226, 235), outline=SLOW_DARK, width=3)
    _fast(draw, (cx - 178, cy + 40), scale=1.18)
    _slow(draw, (cx + 116, cy + 46), scale=1.08, lounging=True)
    draw.line((x0 + 120, y0 + 286, x1 - 120, y0 + 286), fill=(178, 160, 136), width=4)


def _scene_fast(draw: ImageDraw.ImageDraw, art: tuple[int, int, int, int], fonts: dict[str, ImageFont.FreeTypeFont], blank_text: bool) -> None:
    x0, y0, x1, y1 = art
    _fast(draw, (x0 + 148, y0 + 202), scale=1.55)
    _icon_card(draw, (x0 + 330, y0 + 42, x0 + 500, y0 + 132), "" if blank_text else "+", WARM, fonts["title"])
    _traffic_light(draw, (x0 + 370, y0 + 165))
    _icon_card(draw, (x0 + 330, y0 + 272, x0 + 500, y0 + 362), "" if blank_text else "☺", GREEN, fonts["title"])


def _scene_slow(draw: ImageDraw.ImageDraw, art: tuple[int, int, int, int], fonts: dict[str, ImageFont.FreeTypeFont], blank_text: bool) -> None:
    x0, y0, x1, y1 = art
    draw.rounded_rectangle((x0 + 302, y0 + 52, x0 + 522, y0 + 150), radius=14, fill=(246, 241, 231), outline=PANEL_LINE, width=3)
    if not blank_text:
        draw.text((x0 + 334, y0 + 75), "17×24 = ?", font=fonts["beat"], fill=MUTED)
    _slow(draw, (x0 + 210, y0 + 248), scale=1.65, lounging=True)
    _sweat(draw, x0 + 420, y0 + 220)


def _scene_stamp(draw: ImageDraw.ImageDraw, art: tuple[int, int, int, int], fonts: dict[str, ImageFont.FreeTypeFont], blank_text: bool) -> None:
    x0, y0, x1, y1 = art
    _fast(draw, (x0 + 150, y0 + 240), scale=1.35)
    _slow(draw, (x0 + 420, y0 + 244), scale=1.25, lounging=True)
    draw.rounded_rectangle((x0 + 235, y0 + 120, x0 + 350, y0 + 180), radius=12, fill=(255, 255, 255), outline=PANEL_LINE, width=3)
    draw.line((x0 + 224, y0 + 178, x0 + 190, y0 + 207), fill=FAST, width=6)
    draw.rounded_rectangle((x0 + 400, y0 + 118, x0 + 520, y0 + 178), radius=10, fill=(235, 245, 255), outline=SLOW_DARK, width=4)
    if not blank_text:
        draw.text((x0 + 421, y0 + 130), "准了", font=fonts["beat"], fill=SLOW_DARK)


def _scene_anchor_price(draw: ImageDraw.ImageDraw, art: tuple[int, int, int, int], fonts: dict[str, ImageFont.FreeTypeFont], blank_text: bool) -> None:
    x0, y0, x1, y1 = art
    draw.rounded_rectangle((x0 + 48, y0 + 56, x0 + 360, y0 + 226), radius=22, fill=(255, 255, 255), outline=PANEL_LINE, width=3)
    draw.line((x0 + 78, y0 + 103, x0 + 242, y0 + 103), fill=FAST, width=5)
    if not blank_text:
        draw.text((x0 + 78, y0 + 78), "原价 ¥999", font=fonts["beat"], fill=MUTED)
        draw.text((x0 + 78, y0 + 138), "现价 ¥299", font=fonts["title"], fill=FAST)
    _fast(draw, (x0 + 460, y0 + 250), scale=1.45, arms_up=True)


def _scene_checkout(draw: ImageDraw.ImageDraw, art: tuple[int, int, int, int], fonts: dict[str, ImageFont.FreeTypeFont], blank_text: bool) -> None:
    x0, y0, x1, y1 = art
    draw.rounded_rectangle((x0 + 60, y0 + 50, x0 + 290, y0 + 340), radius=28, fill=(247, 248, 248), outline=(180, 180, 180), width=4)
    draw.rounded_rectangle((x0 + 92, y0 + 92, x0 + 258, y0 + 190), radius=12, fill=(230, 236, 242))
    draw.ellipse((x0 + 132, y0 + 222, x0 + 218, y0 + 308), fill=GREEN)
    draw.line((x0 + 152, y0 + 266, x0 + 174, y0 + 286), fill=(255, 255, 255), width=8)
    draw.line((x0 + 174, y0 + 286, x0 + 204, y0 + 244), fill=(255, 255, 255), width=8)
    _slow(draw, (x0 + 450, y0 + 262), scale=1.45, lounging=True)


def _scene_merchant_anchor(draw: ImageDraw.ImageDraw, art: tuple[int, int, int, int], fonts: dict[str, ImageFont.FreeTypeFont], blank_text: bool) -> None:
    x0, y0, x1, y1 = art
    draw.rectangle((x0 + 42, y0 + 30, x0 + 216, y1 - 20), fill=(205, 86, 64))
    draw.rectangle((x1 - 216, y0 + 30, x1 - 42, y1 - 20), fill=(205, 86, 64))
    draw.ellipse((x0 + 262, y0 + 60, x0 + 378, y0 + 176), fill=(245, 206, 160), outline=INK, width=3)
    draw.arc((x0 + 286, y0 + 100, x0 + 354, y0 + 154), 0, 180, fill=INK, width=4)
    _anchor(draw, (x0 + 420, y0 + 86), scale=1.25)
    _fast(draw, (x0 + 170, y0 + 282), scale=1.05)
    _slow(draw, (x0 + 332, y0 + 306), scale=0.95, lounging=True)


def _scene_wake_slow(draw: ImageDraw.ImageDraw, art: tuple[int, int, int, int], fonts: dict[str, ImageFont.FreeTypeFont], blank_text: bool) -> None:
    x0, y0, x1, y1 = art
    _alarm(draw, (x0 + 120, y0 + 90))
    _slow(draw, (x0 + 290, y0 + 260), scale=1.3)
    _fast(draw, (x0 + 510, y0 + 278), scale=0.95)
    draw.rounded_rectangle((x0 + 382, y0 + 72, x0 + 548, y0 + 170), radius=16, fill=(255, 255, 255), outline=PANEL_LINE, width=3)
    draw.line((x0 + 408, y0 + 128, x0 + 522, y0 + 128), fill=MUTED, width=4)
    if not blank_text:
        draw.text((x0 + 425, y0 + 86), "值多少？", font=fonts["beat"], fill=INK)


def _fast(draw: ImageDraw.ImageDraw, center: tuple[int, int], scale: float = 1.0, arms_up: bool = False) -> None:
    cx, cy = center
    r = int(30 * scale)
    body_h = int(68 * scale)
    line_w = max(2, int(3 * scale))
    limb_w = max(3, int(5 * scale))
    body_box = (cx - int(26 * scale), cy - body_h, cx + int(32 * scale), cy - int(8 * scale))
    head_box = (cx - r, cy - body_h - r * 2, cx + r, cy - body_h)
    hand_r = max(4, int(6 * scale))

    draw.line((cx - int(14 * scale), cy - int(8 * scale), cx - int(36 * scale), cy + int(34 * scale)), fill=DARK_TROUSERS, width=limb_w)
    draw.line((cx + int(16 * scale), cy - int(8 * scale), cx + int(42 * scale), cy + int(34 * scale)), fill=DARK_TROUSERS, width=limb_w)
    draw.ellipse((cx - int(42 * scale), cy + int(28 * scale), cx - int(25 * scale), cy + int(39 * scale)), fill=BLACK_SHOE)
    draw.ellipse((cx + int(34 * scale), cy + int(28 * scale), cx + int(50 * scale), cy + int(39 * scale)), fill=BLACK_SHOE)

    if arms_up:
        left_hand = (cx - int(54 * scale), cy - int(106 * scale))
        right_hand = (cx + int(62 * scale), cy - int(104 * scale))
        draw.line((cx - int(24 * scale), cy - int(58 * scale), *left_hand), fill=FAST, width=limb_w)
        draw.line((cx + int(28 * scale), cy - int(56 * scale), *right_hand), fill=FAST, width=limb_w)
    else:
        left_hand = (cx - int(58 * scale), cy - int(34 * scale))
        right_hand = (cx + int(62 * scale), cy - int(36 * scale))
        draw.line((cx - int(26 * scale), cy - int(56 * scale), *left_hand), fill=FAST, width=limb_w)
        draw.line((cx + int(28 * scale), cy - int(56 * scale), *right_hand), fill=FAST, width=limb_w)
    for hx, hy in (left_hand, right_hand):
        draw.ellipse((hx - hand_r, hy - hand_r, hx + hand_r, hy + hand_r), fill=SKIN, outline=INK, width=max(1, int(2 * scale)))

    draw.rounded_rectangle(body_box, radius=int(18 * scale), fill=FAST, outline=INK, width=line_w)
    draw.rounded_rectangle(
        (cx - int(9 * scale), cy - body_h + int(10 * scale), cx + int(12 * scale), cy - int(10 * scale)),
        radius=int(6 * scale),
        fill=CREAM_SHIRT,
        outline=None,
    )
    draw.polygon(
        (
            (cx - int(5 * scale), cy - body_h + int(18 * scale)),
            (cx + int(8 * scale), cy - body_h + int(18 * scale)),
            (cx + int(1 * scale), cy - body_h + int(32 * scale)),
            (cx + int(10 * scale), cy - body_h + int(32 * scale)),
            (cx - int(4 * scale), cy - body_h + int(52 * scale)),
        ),
        fill=(255, 218, 71),
    )

    draw.ellipse(head_box, fill=SKIN, outline=INK, width=line_w)
    draw.ellipse((cx - int(12 * scale), cy - body_h - int(28 * scale), cx - int(4 * scale), cy - body_h - int(20 * scale)), fill=INK)
    draw.ellipse((cx + int(8 * scale), cy - body_h - int(28 * scale), cx + int(16 * scale), cy - body_h - int(20 * scale)), fill=INK)
    draw.arc((cx - int(16 * scale), cy - body_h - int(16 * scale), cx + int(20 * scale), cy - body_h + int(8 * scale)), 0, 150, fill=INK, width=line_w)


def _slow(draw: ImageDraw.ImageDraw, center: tuple[int, int], scale: float = 1.0, lounging: bool = False) -> None:
    cx, cy = center
    r = int(31 * scale)
    body_w = int(72 * scale)
    body_h = int(62 * scale)
    line_w = max(2, int(3 * scale))
    if lounging:
        draw.rounded_rectangle((cx - body_w, cy - body_h, cx + body_w, cy), radius=int(26 * scale), fill=SLOW, outline=SLOW_DARK, width=line_w)
        draw.rounded_rectangle((cx - int(25 * scale), cy - body_h + int(10 * scale), cx + int(25 * scale), cy - int(8 * scale)), radius=int(10 * scale), fill=CREAM_SHIRT)
        head_box = (cx - int(36 * scale), cy - body_h - int(58 * scale), cx + int(36 * scale), cy - body_h + int(14 * scale))
        for hx in (cx - body_w + int(18 * scale), cx + body_w - int(18 * scale)):
            draw.ellipse((hx - int(6 * scale), cy - int(18 * scale), hx + int(6 * scale), cy - int(6 * scale)), fill=SKIN, outline=INK, width=max(1, int(2 * scale)))
    else:
        draw.line((cx - int(12 * scale), cy - int(2 * scale), cx - int(24 * scale), cy + int(34 * scale)), fill=DARK_TROUSERS, width=max(3, int(5 * scale)))
        draw.line((cx + int(12 * scale), cy - int(2 * scale), cx + int(24 * scale), cy + int(34 * scale)), fill=DARK_TROUSERS, width=max(3, int(5 * scale)))
        draw.rounded_rectangle((cx - int(34 * scale), cy - body_h, cx + int(34 * scale), cy), radius=int(20 * scale), fill=SLOW, outline=SLOW_DARK, width=line_w)
        draw.rounded_rectangle((cx - int(12 * scale), cy - body_h + int(8 * scale), cx + int(12 * scale), cy - int(6 * scale)), radius=int(5 * scale), fill=CREAM_SHIRT)
        head_box = (cx - r, cy - body_h - r * 2, cx + r, cy - body_h)
        for hx in (cx - int(42 * scale), cx + int(42 * scale)):
            draw.ellipse((hx - int(5 * scale), cy - int(42 * scale), hx + int(5 * scale), cy - int(32 * scale)), fill=SKIN, outline=INK, width=max(1, int(2 * scale)))
    draw.ellipse(head_box, fill=SKIN, outline=SLOW_DARK, width=line_w)
    hx0, hy0, hx1, hy1 = head_box
    ey = hy0 + int((hy1 - hy0) * 0.48)
    for ex in (hx0 + int((hx1 - hx0) * 0.36), hx0 + int((hx1 - hx0) * 0.64)):
        draw.ellipse((ex - int(11 * scale), ey - int(9 * scale), ex + int(11 * scale), ey + int(9 * scale)), outline=INK, width=line_w)
        draw.line((ex - int(8 * scale), ey + int(20 * scale), ex + int(8 * scale), ey + int(20 * scale)), fill=(40, 86, 130), width=max(1, int(2 * scale)))
    draw.line((hx0 + int((hx1 - hx0) * 0.47), ey, hx0 + int((hx1 - hx0) * 0.53), ey), fill=INK, width=max(1, int(2 * scale)))
    draw.arc((hx0 + int(18 * scale), hy0 + int(46 * scale), hx1 - int(18 * scale), hy1 - int(8 * scale)), 20, 160, fill=INK, width=line_w)


def _speech(
    draw: ImageDraw.ImageDraw,
    art: tuple[int, int, int, int],
    text: str,
    fonts: dict[str, ImageFont.FreeTypeFont],
    side: str,
    blank_text: bool,
) -> None:
    x0, y0, x1, y1 = art
    if side == "right":
        box = (x0 + 284, y0 + 20, x1 - 8, y0 + 116)
    else:
        box = (x0 + 20, y0 + 20, x0 + 306, y0 + 116)
    draw.rounded_rectangle(box, radius=22, fill=(255, 255, 255), outline=PANEL_LINE, width=3)
    if not blank_text:
        _multiline(draw, text, (box[0] + 16, box[1] + 12), box[2] - box[0] - 32, fonts["dialogue"], INK, line_gap=4)


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
            lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines


def _text_w(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _text_h(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[3] - box[1]


def _icon_card(draw: ImageDraw.ImageDraw, rect: tuple[int, int, int, int], symbol: str, color: tuple[int, int, int], font: ImageFont.FreeTypeFont) -> None:
    draw.rounded_rectangle(rect, radius=16, fill=(255, 255, 255), outline=PANEL_LINE, width=3)
    x0, y0, x1, y1 = rect
    tw = _text_w(draw, symbol, font)
    th = _text_h(draw, symbol, font)
    draw.text(((x0 + x1 - tw) // 2, (y0 + y1 - th) // 2 - 6), symbol, font=font, fill=color)


def _traffic_light(draw: ImageDraw.ImageDraw, pos: tuple[int, int]) -> None:
    x, y = pos
    draw.rounded_rectangle((x, y, x + 92, y + 166), radius=30, fill=(59, 62, 66))
    for i, color in enumerate(((222, 83, 67), (237, 190, 78), (80, 165, 96))):
        cy = y + 38 + i * 48
        draw.ellipse((x + 28, cy - 17, x + 64, cy + 17), fill=color)


def _sweat(draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
    draw.ellipse((x, y, x + 16, y + 26), fill=(96, 169, 220))
    draw.ellipse((x + 32, y + 24, x + 44, y + 46), fill=(96, 169, 220))


def _anchor(draw: ImageDraw.ImageDraw, pos: tuple[int, int], scale: float) -> None:
    x, y = pos
    s = scale
    draw.ellipse((x, y, x + int(42 * s), y + int(42 * s)), outline=INK, width=int(5 * s))
    draw.line((x + int(21 * s), y + int(42 * s), x + int(21 * s), y + int(170 * s)), fill=INK, width=int(8 * s))
    draw.line((x - int(48 * s), y + int(112 * s), x + int(90 * s), y + int(112 * s)), fill=INK, width=int(8 * s))
    draw.arc((x - int(58 * s), y + int(70 * s), x + int(100 * s), y + int(220 * s)), 20, 160, fill=INK, width=int(8 * s))
    draw.line((x - int(44 * s), y + int(150 * s), x - int(62 * s), y + int(118 * s)), fill=INK, width=int(8 * s))
    draw.line((x + int(86 * s), y + int(150 * s), x + int(104 * s), y + int(118 * s)), fill=INK, width=int(8 * s))


def _alarm(draw: ImageDraw.ImageDraw, pos: tuple[int, int]) -> None:
    x, y = pos
    draw.ellipse((x, y, x + 104, y + 104), fill=(255, 255, 255), outline=INK, width=4)
    draw.ellipse((x - 16, y - 20, x + 28, y + 24), fill=WARM, outline=INK, width=3)
    draw.ellipse((x + 76, y - 20, x + 120, y + 24), fill=WARM, outline=INK, width=3)
    draw.line((x + 52, y + 52, x + 52, y + 20), fill=INK, width=4)
    draw.line((x + 52, y + 52, x + 78, y + 66), fill=INK, width=4)


if __name__ == "__main__":
    render_thinking_fast_and_slow_comic("outputs/images/thinking-fast-and-slow-comic.png")
