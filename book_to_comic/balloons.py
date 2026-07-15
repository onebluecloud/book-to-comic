"""In-art speech balloons and SFX lettering.

The host LLM looks at each approved panel image and writes
``story/balloon_plan.json`` with normalized coordinates (0-1 relative to the
panel art). This module validates that plan deterministically and renders
balloons/SFX onto the art rectangle during composition.

The image model never draws readable text; balloons and SFX stay a
post-production layer, same as captions.
"""

from __future__ import annotations

import colorsys
import json
import math
import random
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from .fonts import find_cjk_font, load_variant

BALLOON_PLAN_FILENAME = "balloon_plan.json"
BALLOON_TYPES = ("speech", "thought", "shout", "whisper", "narration_box")
SFX_STYLES = ("impact", "soft")
MAX_BALLOONS_PER_PANEL = 4
MAX_BALLOON_CHARS = 60
MAX_SFX_PER_PANEL = 2
MAX_SFX_CHARS = 6
_LINE_START_FORBIDDEN = set("，。！？；：、）】》」』’”…—.,!?;:)]}%")
_LINE_END_FORBIDDEN = set("（【《「『‘“([{")


@dataclass(frozen=True)
class BalloonSpec:
    balloon_id: str
    kind: str
    text: str
    speaker: str
    anchor: tuple[float, float]
    box: tuple[float, float, float, float]
    tail: bool
    reading_order: int


@dataclass(frozen=True)
class SfxSpec:
    text: str
    anchor: tuple[float, float]
    angle: float = 0.0
    scale: float = 1.0
    style: str = "impact"


@dataclass(frozen=True)
class NoGoBox:
    """A region the host marked as untouchable while inspecting the panel:
    faces, hands, the action subject. Normalized panel coordinates."""

    box: tuple[float, float, float, float]
    label: str = ""

    @property
    def is_face(self) -> bool:
        lowered = self.label.lower()
        return "face" in lowered or "脸" in self.label or "头" in self.label


@dataclass(frozen=True)
class BalloonStyleProfile:
    """Per-art-style balloon rendering parameters (nine_styles.json balloon_style).

    fill_strategy: "classic" keeps the flat white fill; "adaptive" samples the
    art under each balloon and, on dark painterly panels, fills with a bright
    low-saturation tint of the local hue instead of sticker-white.
    """

    fill_strategy: str = "classic"
    cloud_lobe_scale: float = 0.30
    burst_spikes: int = 14
    burst_amplitude: float = 0.14
    outline_scale: float = 1.0
    speech_jitter: float = 0.0


DEFAULT_BALLOON_PROFILE = BalloonStyleProfile()

_PROFILE_CACHE: dict[str, BalloonStyleProfile] = {}


def profile_for_style(style_id: str | None) -> BalloonStyleProfile:
    """Balloon profile for an art style (renderer defaults when unknown)."""
    if not style_id:
        return DEFAULT_BALLOON_PROFILE
    cached = _PROFILE_CACHE.get(style_id)
    if cached is not None:
        return cached
    try:
        from .styles import balloon_style_for  # lazy: keep balloons importable standalone

        profile = balloon_profile_from_dict(balloon_style_for(style_id))
    except Exception:  # noqa: BLE001 - style registry problems must never break rendering
        profile = DEFAULT_BALLOON_PROFILE
    _PROFILE_CACHE[style_id] = profile
    return profile


def balloon_profile_from_dict(data: object) -> BalloonStyleProfile:
    """Tolerant parser: unknown/missing keys fall back to defaults."""
    if not isinstance(data, dict):
        return DEFAULT_BALLOON_PROFILE
    def _f(key: str, default: float) -> float:
        try:
            return float(data.get(key, default))
        except (TypeError, ValueError):
            return default
    strategy = str(data.get("fill_strategy") or "classic").strip().lower()
    if strategy not in {"classic", "adaptive"}:
        strategy = "classic"
    return BalloonStyleProfile(
        fill_strategy=strategy,
        cloud_lobe_scale=min(0.45, max(0.18, _f("cloud_lobe_scale", 0.30))),
        burst_spikes=int(min(28, max(10, _f("burst_spikes", 14)))),
        burst_amplitude=min(0.22, max(0.06, _f("burst_amplitude", 0.14))),
        outline_scale=min(1.6, max(0.6, _f("outline_scale", 1.0))),
        speech_jitter=min(0.03, max(0.0, _f("speech_jitter", 0.0))),
    )


@dataclass(frozen=True)
class PanelBalloonPlan:
    panel_id: str
    panel_index: int
    balloons: tuple[BalloonSpec, ...] = ()
    sfx: tuple[SfxSpec, ...] = ()
    no_go_boxes: tuple[NoGoBox, ...] = ()


@dataclass(frozen=True)
class BalloonPlan:
    schema_version: str
    episode_id: str
    panels: tuple[PanelBalloonPlan, ...] = ()
    by_index: dict[int, PanelBalloonPlan] = field(default_factory=dict)
    writing_mode: str = "horizontal"


def balloon_plan_path(root: Path) -> Path:
    return Path(root) / "story" / BALLOON_PLAN_FILENAME


def load_balloon_plan(root: str | Path) -> BalloonPlan | None:
    """Load the balloon plan if present; None means compose falls back to captions only."""
    path = balloon_plan_path(Path(root))
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Balloon plan must be a JSON object: {path}")
    panels: list[PanelBalloonPlan] = []
    for raw in payload.get("panels", []):
        if not isinstance(raw, dict):
            raise ValueError("Every balloon plan panel entry must be an object.")
        panels.append(_parse_panel(raw))
    writing_mode = str(payload.get("writing_mode") or "horizontal").strip().lower()
    if writing_mode not in {"horizontal", "vertical"}:
        raise ValueError(f"balloon plan writing_mode must be horizontal or vertical, got {writing_mode!r}")
    plan = BalloonPlan(
        schema_version=str(payload.get("schema_version") or "1.0"),
        episode_id=str(payload.get("episode_id") or "EP01"),
        panels=tuple(panels),
        by_index={panel.panel_index: panel for panel in panels},
        writing_mode=writing_mode,
    )
    return plan


def _parse_panel(raw: dict[str, Any]) -> PanelBalloonPlan:
    index = int(raw.get("panel_index") or 0)
    balloons: list[BalloonSpec] = []
    for position, item in enumerate(raw.get("balloons", []), start=1):
        if not isinstance(item, dict):
            raise ValueError(f"panel {index}: balloon entries must be objects.")
        anchor = item.get("anchor") or {}
        box = item.get("box") or {}
        balloons.append(
            BalloonSpec(
                balloon_id=str(item.get("balloon_id") or f"B{position:02d}"),
                kind=str(item.get("type") or "speech"),
                text=str(item.get("text") or "").strip(),
                speaker=str(item.get("speaker") or "").strip(),
                anchor=(float(anchor.get("x", 0.5)), float(anchor.get("y", 0.5))),
                box=(
                    float(box.get("x", 0.05)),
                    float(box.get("y", 0.05)),
                    float(box.get("w", 0.4)),
                    float(box.get("h", 0.2)),
                ),
                tail=bool(item.get("tail", True)),
                reading_order=int(item.get("reading_order") or position),
            )
        )
    sfx: list[SfxSpec] = []
    for item in raw.get("sfx", []):
        if not isinstance(item, dict):
            raise ValueError(f"panel {index}: sfx entries must be objects.")
        anchor = item.get("anchor") or {}
        sfx.append(
            SfxSpec(
                text=str(item.get("text") or "").strip(),
                anchor=(float(anchor.get("x", 0.5)), float(anchor.get("y", 0.4))),
                angle=float(item.get("angle", 0.0)),
                scale=float(item.get("scale", 1.0)),
                style=str(item.get("style") or "impact"),
            )
        )
    no_go: list[NoGoBox] = []
    for item in raw.get("no_go_boxes", []):
        if not isinstance(item, dict):
            raise ValueError(f"panel {index}: no_go_boxes entries must be objects.")
        no_go.append(
            NoGoBox(
                box=(
                    float(item.get("x", 0.0)),
                    float(item.get("y", 0.0)),
                    float(item.get("w", 0.0)),
                    float(item.get("h", 0.0)),
                ),
                label=str(item.get("label") or "").strip(),
            )
        )
    return PanelBalloonPlan(
        panel_id=str(raw.get("panel_id") or f"P{index:02d}"),
        panel_index=index,
        balloons=tuple(balloons),
        sfx=tuple(sfx),
        no_go_boxes=tuple(no_go),
    )


def normalize_balloon_line(text: str) -> str:
    """Normalize a dialogue line for matching: strip speaker prefix and whitespace."""
    cleaned = "".join(str(text).split())
    for separator in ("：", ":"):
        head, mid, tail = cleaned.partition(separator)
        if mid and head and len(head) <= 8 and tail:
            cleaned = tail
            break
    return cleaned.strip("「」\"'“”")


def panel_balloon_lines(plan_panel: PanelBalloonPlan | None) -> set[str]:
    """Normalized balloon texts of one panel, for caption dedupe."""
    if plan_panel is None:
        return set()
    return {normalize_balloon_line(balloon.text) for balloon in plan_panel.balloons if balloon.text}


_DEDUPE_QUOTE_CHARS = "「」『』\"'“”‘’"
_DEDUPE_TRAILING = "。．.！!？?，,、；;"
_MAX_DEDUPE_RUN = 4


def _dedupe_key(text: str) -> str:
    """Match key for caption-vs-balloon dedupe.

    Unlike :func:`normalize_balloon_line` this drops quote marks wherever they
    appear and trailing punctuation, because ``card_form`` may author a single
    spoken line as two consecutive caption entries -- leaving an unbalanced
    ``「`` on the first and ``」。`` on the second. Neither entry matches the
    balloon on its own, so the pair has to be joined before comparing.
    """
    cleaned = "".join(str(text).split())
    for separator in ("：", ":"):
        head, mid, tail = cleaned.partition(separator)
        if mid and head and len(head) <= 8 and tail:
            cleaned = tail
            break
    cleaned = "".join(char for char in cleaned if char not in _DEDUPE_QUOTE_CHARS)
    return cleaned.rstrip(_DEDUPE_TRAILING)


LETTERING_MODES = ("balloon", "hybrid", "caption-only")
DEFAULT_LETTERING_MODE = "balloon"


def resolve_lettering_mode(value: object) -> str:
    """Normalize a configured lettering mode, defaulting to in-image balloons."""
    if value is None or value == "":
        return DEFAULT_LETTERING_MODE
    mode = str(value).strip().lower().replace("_", "-")
    if mode not in LETTERING_MODES:
        raise ValueError(f"lettering_mode must be one of {', '.join(LETTERING_MODES)}; got {value!r}")
    return mode


def draws_balloons(mode: str) -> bool:
    return resolve_lettering_mode(mode) == "balloon"


def draws_sfx(mode: str) -> bool:
    """SFX belong to the artwork -- they stay in-image everywhere except caption-only."""
    return resolve_lettering_mode(mode) in {"balloon", "hybrid"}


def filter_panel_for_mode(plan_panel: PanelBalloonPlan, mode: str) -> PanelBalloonPlan:
    """Drop the overlays a mode does not draw, so renderers need no mode logic."""
    return replace(
        plan_panel,
        balloons=plan_panel.balloons if draws_balloons(mode) else (),
        sfx=plan_panel.sfx if draws_sfx(mode) else (),
    )


def caption_lines_for_mode(
    lines: Sequence[str],
    plan_panel: PanelBalloonPlan | None,
    mode: str = DEFAULT_LETTERING_MODE,
) -> tuple[str, ...]:
    """Caption text for one panel under a lettering mode.

    ``balloon`` removes lines the balloon already shows. The other modes do not
    draw balloons, so their text has to survive in the caption -- normally it is
    already there (balloon text is authored from the panel's dialogue), but a
    missing line is appended rather than silently dropped.
    """
    if draws_balloons(mode):
        return strip_ballooned_lines(lines, plan_panel)
    result = list(lines)
    if plan_panel is None:
        return tuple(result)
    present = {_dedupe_key(line) for line in result}
    for balloon in plan_panel.balloons:
        key = _dedupe_key(balloon.text)
        if key and key not in present:
            result.append(balloon.text)
            present.add(key)
    return tuple(result)


def strip_ballooned_lines(
    lines: Sequence[str],
    plan_panel: PanelBalloonPlan | None,
) -> tuple[str, ...]:
    """Drop caption lines whose text is already rendered inside a balloon.

    Matches the longest run of consecutive caption lines first, so a spoken line
    split across two entries is removed as a unit rather than surviving because
    neither half matches on its own.
    """
    if plan_panel is None:
        return tuple(lines)
    keys = {_dedupe_key(balloon.text) for balloon in plan_panel.balloons if balloon.text}
    keys.discard("")
    if not keys:
        return tuple(lines)
    source = list(lines)
    kept: list[str] = []
    index = 0
    while index < len(source):
        matched = 0
        for end in range(min(index + _MAX_DEDUPE_RUN, len(source)), index, -1):
            if _dedupe_key("".join(source[index:end])) in keys:
                matched = end - index
                break
        if matched:
            index += matched
            continue
        kept.append(source[index])
        index += 1
    return tuple(kept)


def effective_char_units(text: str) -> float:
    """CJK chars count 1.0, halfwidth chars 0.55 — the unit of the em grid."""
    units = 0.0
    for char in str(text):
        units += 1.0 if ord(char) > 0x2E7F else 0.55
    return max(1.0, units)


def estimate_balloon_box(
    text: str,
    panel_size: tuple[int, int],
    writing_mode: str = "horizontal",
    *,
    purpose: str = "page",
) -> dict[str, Any]:
    """Text → normalized balloon box size, before choosing where to put it.

    Em-grid model for square CJK glyphs: em = clamp(0.028 * min(W,H), 16, 40)
    for page comics (0.034 / 20-48 for webtoon), cols = clamp(round(sqrt(1.8u)),
    4, 14), padding 0.65em / 0.75em. ``split_required`` mirrors the validator's
    thresholds so the host splits the line instead of shipping an oversized box.
    """
    width, height = max(1, panel_size[0]), max(1, panel_size[1])
    short_side = min(width, height)
    if purpose == "webtoon":
        em = max(20, min(48, int(short_side * 0.034)))
    else:
        em = max(16, min(40, int(short_side * 0.028)))
    units = effective_char_units(_strip_speaker_prefix(str(text)))
    per_line = max(4, min(14, round(math.sqrt(1.8 * units))))
    lines = math.ceil(units / per_line)
    if writing_mode == "vertical":
        text_w = lines * 1.18 * em
        text_h = per_line * em
    else:
        text_w = per_line * em
        text_h = lines * 1.20 * em
    pad_x = 0.65 * em
    pad_y = 0.75 * em
    # ellipse breathing room matches the renderer's 1.22 / 1.30 expansion
    box_w = min(width * 0.9, (text_w + 2 * pad_x) * 1.22)
    box_h = min(height * 0.9, (text_h + 2 * pad_y) * 1.30)
    norm_w = box_w / width
    norm_h = box_h / height
    area = norm_w * norm_h
    split = area > MAX_BALLOON_AREA_RATIO or (writing_mode == "vertical" and lines > 4) or (writing_mode != "vertical" and lines > 5)
    return {
        "em_px": em,
        "chars_per_line": per_line,
        "line_count": lines,
        "box_w": round(norm_w, 4),
        "box_h": round(norm_h, 4),
        "area_ratio": round(area, 4),
        "split_required": split,
    }


def suggest_clear_position(
    box_wh: tuple[float, float],
    no_go_boxes: Sequence[NoGoBox],
    taken_boxes: Sequence[tuple[float, float, float, float]] = (),
    *,
    near: tuple[float, float] | None = None,
    margin: float = 0.02,
) -> tuple[float, float] | None:
    """Grid-scan for a spot where a ``box_wh``-sized balloon violates nothing.

    Returns the top-left (x, y) closest to ``near`` (speaker anchor or original
    center), or None when the panel genuinely has no room — the caller should
    then split the text or fall back to a caption.
    """
    bw, bh = box_wh
    if bw >= 1.0 or bh >= 1.0:
        return None
    best: tuple[float, tuple[float, float]] | None = None
    target = near or (0.5, 0.5)
    steps = 24
    for iy in range(steps + 1):
        y = margin + (1.0 - bh - 2 * margin) * iy / steps
        if y < 0:
            continue
        for ix in range(steps + 1):
            x = margin + (1.0 - bw - 2 * margin) * ix / steps
            if x < 0:
                continue
            candidate = (x, y, bw, bh)
            if any(box_overlap_ratio(candidate, ng.box) > (FACE_OVERLAP_LIMIT if ng.is_face else SUBJECT_OVERLAP_LIMIT) for ng in no_go_boxes):
                continue
            if any(box_overlap_ratio(candidate, taken) > 0 or box_gap(candidate, taken) < MIN_BALLOON_GAP for taken in taken_boxes):
                continue
            cx, cy = x + bw / 2, y + bh / 2
            dist = math.hypot(cx - target[0], cy - target[1])
            if best is None or dist < best[0]:
                best = (dist, (round(x, 3), round(y, 3)))
    return best[1] if best else None


# ---- placement geometry (shared by the validator and the future auto-placer;
# ---- each check here is one term of the placement energy function) ----

MAX_BALLOON_AREA_RATIO = 0.14   # single-balloon share of the panel (page-comic profile)
MIN_BALLOON_GAP = 0.015         # normalized min gap between balloon boxes
FACE_OVERLAP_LIMIT = 0.0        # faces are inviolable
SUBJECT_OVERLAP_LIMIT = 0.08    # hands / action subject tolerate slivers


def box_overlap_ratio(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    """Share of box ``b`` covered by box ``a`` (both x, y, w, h normalized)."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    if bw <= 0 or bh <= 0:
        return 0.0
    ix = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    return (ix * iy) / (bw * bh)


def box_gap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    """Smallest normalized gap between two boxes; 0 when they touch or overlap."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    dx = max(0.0, max(ax, bx) - min(ax + aw, bx + bw))
    dy = max(0.0, max(ay, by) - min(ay + ah, by + bh))
    return math.hypot(dx, dy)


def precedence_violations(
    balloons: Sequence[BalloonSpec],
    writing_mode: str = "horizontal",
) -> list[tuple[str, str]]:
    """Pairs whose reading_order contradicts geometric reading precedence.

    Horizontal Chinese reads top-to-bottom, then left-to-right within a row;
    vertical reads right-to-left, then top-to-bottom within a column. Tolerances
    follow the placement study: tau_x = 0.15 * min(w), tau_y = 0.18 * min(h).
    """
    ordered = sorted(balloons, key=lambda item: item.reading_order)
    bad: list[tuple[str, str]] = []
    for i, earlier in enumerate(ordered):
        for later in ordered[i + 1:]:
            ex, ey, ew, eh = earlier.box
            lx, ly, lw, lh = later.box
            ecx, ecy = ex + ew / 2, ey + eh / 2
            lcx, lcy = lx + lw / 2, ly + lh / 2
            tau_x = 0.15 * min(ew, lw)
            tau_y = 0.18 * min(eh, lh)
            if writing_mode == "vertical":
                # `later` strictly precedes `earlier` when clearly to the right,
                # or in the same column and clearly above.
                reversed_pair = (lcx - tau_x > ecx) or (abs(lcx - ecx) <= tau_x and lcy + tau_y < ecy)
            else:
                reversed_pair = (lcy + tau_y < ecy) or (abs(lcy - ecy) <= tau_y and lcx + tau_x < ecx)
            if reversed_pair:
                bad.append((earlier.balloon_id, later.balloon_id))
    return bad


def _anchor_buried_in_box(balloon: BalloonSpec) -> bool:
    """True when the speaker anchor sits deep inside the balloon's own box —
    the tail then points nowhere and attribution is lost."""
    ax, ay = balloon.anchor
    bx, by, bw, bh = balloon.box
    core_x0 = bx + bw * 0.30
    core_x1 = bx + bw * 0.70
    core_y0 = by + bh * 0.30
    core_y1 = by + bh * 0.70
    return core_x0 <= ax <= core_x1 and core_y0 <= ay <= core_y1


def validate_balloon_plan(
    project_dir: str | Path,
    *,
    panel_dialogue: dict[int, list[str]] | None = None,
    expected_panel_count: int = 0,
    write_report: bool = True,
) -> dict[str, Any]:
    """Deterministic checks on story/balloon_plan.json; writes qa/balloon-plan-report.json."""
    root = Path(project_dir)
    plan = load_balloon_plan(root)
    if plan is None:
        raise FileNotFoundError(
            f"Balloon plan not found: {balloon_plan_path(root)}. "
            "Have the host inspect each approved panel and write it first."
        )
    errors: list[str] = []
    warnings: list[str] = []
    seen_indexes: set[int] = set()
    for panel in plan.panels:
        prefix = f"panel {panel.panel_index}"
        if panel.panel_index < 1:
            errors.append(f"{prefix}: panel_index must be >= 1.")
            continue
        if panel.panel_index in seen_indexes:
            errors.append(f"{prefix}: duplicate panel_index.")
        seen_indexes.add(panel.panel_index)
        if expected_panel_count and panel.panel_index > expected_panel_count:
            errors.append(f"{prefix}: panel_index exceeds panel count {expected_panel_count}.")
        if len(panel.balloons) > MAX_BALLOONS_PER_PANEL:
            errors.append(f"{prefix}: {len(panel.balloons)} balloons exceed the max of {MAX_BALLOONS_PER_PANEL}.")
        if len(panel.sfx) > MAX_SFX_PER_PANEL:
            errors.append(f"{prefix}: {len(panel.sfx)} sfx exceed the max of {MAX_SFX_PER_PANEL}.")
        orders = [balloon.reading_order for balloon in panel.balloons]
        if len(orders) != len(set(orders)):
            errors.append(f"{prefix}: balloon reading_order values must be unique.")
        known_lines = None
        if panel_dialogue is not None:
            known_lines = {normalize_balloon_line(line) for line in panel_dialogue.get(panel.panel_index, [])}
        for balloon in panel.balloons:
            bid = f"{prefix} balloon {balloon.balloon_id}"
            if balloon.kind not in BALLOON_TYPES:
                errors.append(f"{bid}: unknown type '{balloon.kind}'. Allowed: {', '.join(BALLOON_TYPES)}.")
            if not balloon.text:
                errors.append(f"{bid}: text is empty.")
            elif len(balloon.text) > MAX_BALLOON_CHARS:
                errors.append(f"{bid}: text has {len(balloon.text)} chars; max {MAX_BALLOON_CHARS} for readability.")
            if not _unit_interval(balloon.anchor[0]) or not _unit_interval(balloon.anchor[1]):
                errors.append(f"{bid}: anchor must be normalized 0-1 coordinates.")
            bx, by, bw, bh = balloon.box
            if bw <= 0 or bh <= 0 or bx < 0 or by < 0 or bx + bw > 1.001 or by + bh > 1.001:
                errors.append(f"{bid}: box must stay inside the panel (0-1 normalized).")
            if known_lines is not None and balloon.kind in {"speech", "thought", "shout", "whisper"}:
                normalized = normalize_balloon_line(balloon.text)
                if normalized and known_lines and not _matches_any(normalized, known_lines):
                    errors.append(
                        f"{bid}: text does not match any dialogue line of this panel; "
                        "balloons must reuse approved dialogue, not invent new lines."
                    )
        # Placement geometry. Plans that declare no_go_boxes opted into the new
        # placement contract and get hard failures; legacy plans (none declared)
        # get the same checks as warnings so existing projects keep composing.
        strict = bool(panel.no_go_boxes)
        geometry_sink = errors if strict else warnings
        for no_go in panel.no_go_boxes:
            nx, ny, nw, nh = no_go.box
            if nw <= 0 or nh <= 0 or nx < 0 or ny < 0 or nx + nw > 1.001 or ny + nh > 1.001:
                errors.append(f"{prefix}: no_go box '{no_go.label or '?'}' must stay inside the panel (0-1).")
        for balloon in panel.balloons:
            bid = f"{prefix} balloon {balloon.balloon_id}"
            bx, by, bw, bh = balloon.box
            area = bw * bh
            if area > MAX_BALLOON_AREA_RATIO:
                geometry_sink.append(
                    f"{bid}: box covers {area:.2f} of the panel (max {MAX_BALLOON_AREA_RATIO}); "
                    "split the line or shrink the box."
                )
            for no_go in panel.no_go_boxes:
                limit = FACE_OVERLAP_LIMIT if no_go.is_face else SUBJECT_OVERLAP_LIMIT
                ratio = box_overlap_ratio(balloon.box, no_go.box)
                if ratio > limit + 1e-6:
                    others = [b.box for b in panel.balloons if b.balloon_id != balloon.balloon_id]
                    suggestion = suggest_clear_position(
                        (bw, bh), panel.no_go_boxes, others, near=balloon.anchor
                    )
                    hint = (
                        f" Clear spot for the same box size: x={suggestion[0]}, y={suggestion[1]}."
                        if suggestion
                        else " No clear spot fits this box size: split the text or use a caption."
                    )
                    errors.append(
                        f"{bid}: covers {ratio:.0%} of no-go region '{no_go.label or 'subject'}' "
                        f"(limit {limit:.0%}); move the balloon into negative space.{hint}"
                    )
                    break
            if balloon.tail and _anchor_buried_in_box(balloon):
                geometry_sink.append(
                    f"{bid}: speaker anchor sits inside the balloon body, so the tail points nowhere; "
                    "anchor should mark the speaker's mouth/head outside the box."
                )
        ordered = sorted(panel.balloons, key=lambda item: item.reading_order)
        for i, earlier in enumerate(ordered):
            for later in ordered[i + 1:]:
                gap = box_gap(earlier.box, later.box)
                overlap = box_overlap_ratio(earlier.box, later.box)
                if overlap > 0.0:
                    geometry_sink.append(
                        f"{prefix}: balloons {earlier.balloon_id} and {later.balloon_id} overlap; separate them."
                    )
                elif 0.0 < gap < MIN_BALLOON_GAP:
                    warnings.append(
                        f"{prefix}: balloons {earlier.balloon_id} and {later.balloon_id} nearly touch "
                        f"(gap {gap:.3f} < {MIN_BALLOON_GAP}); tangent contact reads as clutter."
                    )
        for earlier_id, later_id in precedence_violations(panel.balloons, plan.writing_mode):
            geometry_sink.append(
                f"{prefix}: balloon {later_id} reads after {earlier_id} but sits earlier in "
                f"{plan.writing_mode} reading order; fix reading_order or reposition."
            )
        for sfx in panel.sfx:
            if not sfx.text:
                errors.append(f"{prefix}: sfx text is empty.")
            elif len(sfx.text) > MAX_SFX_CHARS:
                errors.append(f"{prefix}: sfx '{sfx.text}' is longer than {MAX_SFX_CHARS} chars.")
            if sfx.style not in SFX_STYLES:
                errors.append(f"{prefix}: sfx style '{sfx.style}' unknown. Allowed: {', '.join(SFX_STYLES)}.")
            if not _unit_interval(sfx.anchor[0]) or not _unit_interval(sfx.anchor[1]):
                errors.append(f"{prefix}: sfx anchor must be normalized 0-1 coordinates.")
    if expected_panel_count:
        # A plan covering 1 of 3 panels used to pass (2026-07 audit F8). Every
        # panel must appear — a silent panel keeps an empty balloons[] entry so
        # its silence is an explicit decision, not a gap nobody noticed.
        missing = sorted(set(range(1, expected_panel_count + 1)) - seen_indexes)
        if missing:
            errors.append(
                f"balloon plan must cover every panel 1..{expected_panel_count}; missing panels: "
                + ", ".join(str(index) for index in missing)
                + ". A silent panel still needs an entry with an empty balloons[] list."
            )
    report = {
        "schema_version": "1.0",
        "passed": not errors,
        "panel_count": len(plan.panels),
        "balloon_count": sum(len(panel.balloons) for panel in plan.panels),
        "sfx_count": sum(len(panel.sfx) for panel in plan.panels),
        "errors": errors,
        "warnings": warnings,
    }
    if write_report:
        qa_dir = root / "qa"
        qa_dir.mkdir(parents=True, exist_ok=True)
        (qa_dir / "balloon-plan-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    if errors:
        details = "\n".join(f"- {item}" for item in errors)
        raise ValueError(f"Balloon plan failed validation:\n{details}")
    return report


def _matches_any(normalized: str, known_lines: set[str]) -> bool:
    if normalized in known_lines:
        return True
    return any(normalized in line or line in normalized for line in known_lines if line)


def _unit_interval(value: float) -> bool:
    return -0.001 <= value <= 1.001


# ---------------------------------------------------------------------------
# Rendering


def render_panel_overlays(
    canvas: Image.Image,
    art_rect: tuple[int, int, int, int],
    plan_panel: PanelBalloonPlan,
    *,
    font_family: str = "sans",
    ink: tuple[int, int, int] = (32, 30, 27),
    viewport: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0),
    lettering_mode: str = DEFAULT_LETTERING_MODE,
    profile: BalloonStyleProfile | None = None,
) -> None:
    """Draw balloons and SFX of one panel onto the canvas, clipped to art_rect.

    ``viewport`` is the normalized window of the ORIGINAL panel image that
    art_rect displays. Compose paths that crop the art (ImageOps.fit) pass the
    visible window so plan coordinates keep pointing at the same pixels.

    ``lettering_mode`` decides which overlays exist at all: ``hybrid`` keeps SFX
    in the artwork and sinks dialogue into the caption, ``caption-only`` leaves
    the artwork untouched.

    ``profile`` carries the art style's balloon parameters; adaptive fill samples
    the already-pasted art on ``canvas`` under each balloon.
    """
    plan_panel = filter_panel_for_mode(plan_panel, lettering_mode)
    if not plan_panel.balloons and not plan_panel.sfx:
        return
    profile = profile or DEFAULT_BALLOON_PROFILE
    mapped = _map_plan_to_viewport(plan_panel, viewport)
    x0, y0, x1, y1 = art_rect
    width = max(1, x1 - x0)
    height = max(1, y1 - y0)
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for sfx in mapped.sfx:
        _draw_sfx(layer, sfx, ink=ink)
    for balloon in sorted(mapped.balloons, key=lambda item: item.reading_order):
        backdrop = None
        if profile.fill_strategy == "adaptive":
            backdrop = _sample_backdrop(canvas, art_rect, balloon.box)
        _draw_balloon(draw, layer.size, balloon, font_family=font_family, ink=ink, profile=profile, backdrop=backdrop)
    canvas.paste(layer, (x0, y0), layer)


def _sample_backdrop(
    canvas: Image.Image,
    art_rect: tuple[int, int, int, int],
    box: tuple[float, float, float, float],
) -> tuple[int, int, int] | None:
    """Median-ish color of the art under a balloon box (canvas already holds the art)."""
    ax0, ay0, ax1, ay1 = art_rect
    aw, ah = ax1 - ax0, ay1 - ay0
    px0 = int(ax0 + box[0] * aw)
    py0 = int(ay0 + box[1] * ah)
    px1 = int(px0 + max(1.0, box[2] * aw))
    py1 = int(py0 + max(1.0, box[3] * ah))
    px0 = max(0, min(px0, canvas.width - 1))
    py0 = max(0, min(py0, canvas.height - 1))
    px1 = max(px0 + 1, min(px1, canvas.width))
    py1 = max(py0 + 1, min(py1, canvas.height))
    try:
        region = canvas.crop((px0, py0, px1, py1)).convert("RGB")
    except (OSError, ValueError):
        return None
    # resize to 1x1 approximates the mean; good enough to classify dark vs light
    r, g, b = region.resize((1, 1), Image.Resampling.BILINEAR).getpixel((0, 0))
    return (r, g, b)


def _adaptive_fill(backdrop: tuple[int, int, int] | None) -> tuple[int, int, int, int]:
    """Bright, low-saturation tint of the local hue for dark painterly panels.

    Keeps a whisper of the backdrop's hue (saturation * 0.15) and lifts value
    into paper-white territory, so the balloon reads as part of the plate
    rather than a UI sticker. Light backdrops keep the classic white.
    """
    if backdrop is None:
        return (255, 255, 255, 242)
    r, g, b = backdrop
    luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
    if luma >= 110:
        return (255, 255, 255, 242)
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    nr, ng, nb = colorsys.hsv_to_rgb(h, min(1.0, s) * 0.15, 0.94)
    return (int(nr * 255), int(ng * 255), int(nb * 255), 246)


def fit_crop_viewport(
    source_size: tuple[int, int],
    target_size: tuple[int, int],
    centering: tuple[float, float] = (0.5, 0.5),
) -> tuple[float, float, float, float]:
    """Normalized source window that ImageOps.fit(source, target, centering=...) keeps visible."""
    sw, sh = max(1, source_size[0]), max(1, source_size[1])
    tw, th = max(1, target_size[0]), max(1, target_size[1])
    scale = max(tw / sw, th / sh)
    visible_w = tw / scale
    visible_h = th / scale
    x0 = (sw - visible_w) * centering[0]
    y0 = (sh - visible_h) * centering[1]
    return (x0 / sw, y0 / sh, (x0 + visible_w) / sw, (y0 + visible_h) / sh)


def _map_plan_to_viewport(
    plan_panel: PanelBalloonPlan,
    viewport: tuple[float, float, float, float],
) -> PanelBalloonPlan:
    vx0, vy0, vx1, vy1 = viewport
    if (vx0, vy0, vx1, vy1) == (0.0, 0.0, 1.0, 1.0):
        return plan_panel
    vw = max(1e-6, vx1 - vx0)
    vh = max(1e-6, vy1 - vy0)
    balloons = tuple(
        BalloonSpec(
            balloon_id=balloon.balloon_id,
            kind=balloon.kind,
            text=balloon.text,
            speaker=balloon.speaker,
            anchor=((balloon.anchor[0] - vx0) / vw, (balloon.anchor[1] - vy0) / vh),
            box=(
                (balloon.box[0] - vx0) / vw,
                (balloon.box[1] - vy0) / vh,
                balloon.box[2] / vw,
                balloon.box[3] / vh,
            ),
            tail=balloon.tail,
            reading_order=balloon.reading_order,
        )
        for balloon in plan_panel.balloons
    )
    sfx = tuple(
        SfxSpec(
            text=item.text,
            anchor=((item.anchor[0] - vx0) / vw, (item.anchor[1] - vy0) / vh),
            angle=item.angle,
            scale=item.scale,
            style=item.style,
        )
        for item in plan_panel.sfx
    )
    return PanelBalloonPlan(panel_id=plan_panel.panel_id, panel_index=plan_panel.panel_index, balloons=balloons, sfx=sfx)


def _balloon_fonts(font_family: str, size: int) -> ImageFont.FreeTypeFont:
    if font_family == "serif":
        path = find_cjk_font("regular", extra_candidates=("NotoSerifSC-VF.ttf", "simsun.ttc"))
    else:
        path = find_cjk_font("regular")
    return load_variant(path, size, "regular")


def _sfx_font(size: int) -> ImageFont.FreeTypeFont:
    path = find_cjk_font("bold")
    return load_variant(path, size, "bold")


def _draw_balloon(
    draw: ImageDraw.ImageDraw,
    size: tuple[int, int],
    balloon: BalloonSpec,
    *,
    font_family: str,
    ink: tuple[int, int, int],
    profile: BalloonStyleProfile = DEFAULT_BALLOON_PROFILE,
    backdrop: tuple[int, int, int] | None = None,
) -> None:
    width, height = size
    box_x = balloon.box[0] * width
    box_y = balloon.box[1] * height
    box_w = max(24.0, balloon.box[2] * width)
    box_h = max(24.0, balloon.box[3] * height)

    text = balloon.text
    if balloon.kind in {"speech", "thought", "shout", "whisper"}:
        text = _strip_speaker_prefix(text)

    # Grow the type to fill the box instead of nailing it to box_h*0.34: a box
    # sized generously by the placer used to leave the text shrunk in the middle,
    # and short lines got force-wrapped to 2 rows ("按名/应征"). Search from a
    # large size downward for the biggest font whose wrap fits box height with a
    # sane line count, preferring fewer rows.
    ceiling = max(16, min(int(height * 0.060), int(box_h * 0.52)))
    if balloon.kind == "shout":
        ceiling = int(ceiling * 1.15)
    max_rows = 4

    def _fit(size: int) -> tuple[int, list[str], int]:
        f = _balloon_fonts(font_family, size)
        px = max(14, int(size * 0.75))
        wrapped = _wrap_cjk(draw, text, int(box_w - px * 2), f)
        lh = _line_height(draw, f)
        stack = len(wrapped) * lh + (len(wrapped) - 1) * max(2, size // 6)
        return size, wrapped, stack

    base_size, lines, _stack = _fit(ceiling)
    while base_size > 14:
        size, wrapped, stack = _fit(base_size)
        pad_y_try = max(10, int(size * 0.55))
        if len(wrapped) <= max_rows and stack + pad_y_try * 2 <= box_h:
            base_size, lines = size, wrapped
            break
        base_size -= 2
    else:
        base_size, lines, _ = _fit(14)

    font = _balloon_fonts(font_family, base_size)
    pad_x = max(14, int(base_size * 0.75))
    pad_y = max(10, int(base_size * 0.55))
    line_h = _line_height(draw, font)
    text_w = max((_text_width(draw, line, font) for line in lines), default=base_size)
    text_h = len(lines) * line_h + (len(lines) - 1) * max(2, base_size // 6)

    bubble_w = min(box_w, text_w + pad_x * 2)
    bubble_h = min(box_h, text_h + pad_y * 2)
    # Ellipses need extra room so text corners stay inside the curve.
    if balloon.kind in {"speech", "thought", "shout", "whisper"}:
        bubble_w = min(box_w, bubble_w * 1.22)
        bubble_h = min(box_h, bubble_h * 1.30)
    cx = _clamp(box_x + box_w / 2, bubble_w / 2, width - bubble_w / 2)
    cy = _clamp(box_y + box_h / 2, bubble_h / 2, height - bubble_h / 2)
    rect = (cx - bubble_w / 2, cy - bubble_h / 2, cx + bubble_w / 2, cy + bubble_h / 2)

    fill = _adaptive_fill(backdrop) if profile.fill_strategy == "adaptive" else (255, 255, 255, 242)
    # Slightly translucent stroke reads as drawn-on rather than a razor-cut sticker
    # edge; the heavy lifting against sticker-feel is done upstream by routing
    # painterly styles to external captions.
    outline = (*ink, 238)
    outline_w = max(2, int(min(width, height) * 0.004 * profile.outline_scale))

    if balloon.tail and balloon.kind in {"speech", "shout", "whisper"}:
        _draw_tail(draw, rect, (balloon.anchor[0] * width, balloon.anchor[1] * height), fill, outline, outline_w)

    if balloon.kind == "speech":
        if profile.speech_jitter > 0:
            _draw_jittered_ellipse(draw, rect, fill, outline, outline_w, jitter=profile.speech_jitter, seed=balloon.balloon_id)
        else:
            draw.ellipse(rect, fill=fill, outline=outline, width=outline_w)
    elif balloon.kind == "whisper":
        wr, wg, wb, _ = fill
        draw.ellipse(rect, fill=(wr, wg, wb, 216), outline=(*ink, 150), width=max(1, outline_w - 1))
    elif balloon.kind == "thought":
        _draw_cloud(draw, rect, fill, outline, outline_w, lobe_scale=profile.cloud_lobe_scale)
        if balloon.tail:
            _draw_thought_trail(draw, rect, (balloon.anchor[0] * width, balloon.anchor[1] * height), fill, outline, outline_w)
    elif balloon.kind == "shout":
        _draw_burst(draw, rect, fill, outline, outline_w, spikes=profile.burst_spikes, amplitude=profile.burst_amplitude)
    else:  # narration_box
        draw.rectangle(rect, fill=(252, 248, 236, 240), outline=outline, width=max(1, outline_w - 1))

    text_x0 = cx - text_w / 2
    text_y = cy - text_h / 2
    gap = max(2, base_size // 6)
    text_fill = (*ink, 255)
    for line in lines:
        line_w = _text_width(draw, line, font)
        draw.text((cx - line_w / 2, text_y), line, font=font, fill=text_fill)
        text_y += line_h + gap
    del text_x0


def _draw_tail(
    draw: ImageDraw.ImageDraw,
    rect: tuple[float, float, float, float],
    target: tuple[float, float],
    fill: tuple[int, int, int, int],
    outline: tuple[int, int, int, int],
    outline_w: int,
) -> None:
    cx = (rect[0] + rect[2]) / 2
    cy = (rect[1] + rect[3]) / 2
    rx = (rect[2] - rect[0]) / 2
    ry = (rect[3] - rect[1]) / 2
    dx = target[0] - cx
    dy = target[1] - cy
    distance = math.hypot(dx, dy)
    if distance < 1:
        return
    ux, uy = dx / distance, dy / distance
    # Stop the tail a bit short of the mouth so it points at, not into, the face.
    tip_reach = min(distance * 0.72, distance - 10)
    tip = (cx + ux * tip_reach, cy + uy * tip_reach)
    # Base of the triangle sits on the ellipse edge, perpendicular to the direction.
    edge = (cx + ux * rx * 0.86, cy + uy * ry * 0.86)
    base_half = max(7.0, min(rx, ry) * 0.24)
    px, py = -uy, ux
    p1 = (edge[0] + px * base_half, edge[1] + py * base_half)
    p2 = (edge[0] - px * base_half, edge[1] - py * base_half)
    draw.polygon([p1, p2, tip], fill=fill, outline=outline)
    if outline_w > 1:
        draw.line([p1, tip], fill=outline, width=outline_w - 1)
        draw.line([p2, tip], fill=outline, width=outline_w - 1)


def _draw_thought_trail(
    draw: ImageDraw.ImageDraw,
    rect: tuple[float, float, float, float],
    target: tuple[float, float],
    fill: tuple[int, int, int, int],
    outline: tuple[int, int, int, int],
    outline_w: int,
) -> None:
    cx = (rect[0] + rect[2]) / 2
    cy = (rect[1] + rect[3]) / 2
    for step, radius_ratio in ((0.48, 0.042), (0.66, 0.030), (0.82, 0.020)):
        px = cx + (target[0] - cx) * step
        py = cy + (target[1] - cy) * step
        radius = max(3.0, (rect[2] - rect[0]) * radius_ratio)
        draw.ellipse((px - radius, py - radius, px + radius, py + radius), fill=fill, outline=outline, width=max(1, outline_w - 1))


def _draw_jittered_ellipse(
    draw: ImageDraw.ImageDraw,
    rect: tuple[float, float, float, float],
    fill: tuple[int, int, int, int],
    outline: tuple[int, int, int, int],
    outline_w: int,
    *,
    jitter: float,
    seed: str,
) -> None:
    """Hand-drawn speech ellipse: radius wobbles by up to ``jitter``.

    Seeded by the balloon id so re-composes are pixel-identical.
    """
    cx = (rect[0] + rect[2]) / 2
    cy = (rect[1] + rect[3]) / 2
    rx = (rect[2] - rect[0]) / 2
    ry = (rect[3] - rect[1]) / 2
    rng = random.Random(seed)
    points: list[tuple[float, float]] = []
    steps = 28
    wobbles = [1.0 + rng.uniform(-jitter, jitter) for _ in range(steps)]
    for i in range(steps):
        angle = 2 * math.pi * i / steps
        # average neighboring wobbles to keep the outline smooth, not spiky
        w = (wobbles[i] + wobbles[(i + 1) % steps]) / 2
        points.append((cx + math.cos(angle) * rx * w, cy + math.sin(angle) * ry * w))
    draw.polygon(points, fill=fill, outline=outline)
    if outline_w > 1:
        draw.line(points + [points[0]], fill=outline, width=outline_w - 1)


def _draw_cloud(
    draw: ImageDraw.ImageDraw,
    rect: tuple[float, float, float, float],
    fill: tuple[int, int, int, int],
    outline: tuple[int, int, int, int],
    outline_w: int,
    *,
    lobe_scale: float = 0.30,
) -> None:
    x0, y0, x1, y1 = rect
    w = x1 - x0
    h = y1 - y0
    lobe = max(8.0, min(w, h) * lobe_scale)
    # Outline pass: slightly larger lobes draw the scalloped border.
    for expand, color in ((outline_w * 1.6, outline), (0.0, fill)):
        centers = _cloud_lobes(x0, y0, w, h, lobe)
        for lcx, lcy, lr in centers:
            r = lr + expand
            draw.ellipse((lcx - r, lcy - r, lcx + r, lcy + r), fill=color)
        draw.rounded_rectangle(
            (x0 + lobe * 0.5 - expand, y0 + lobe * 0.5 - expand, x1 - lobe * 0.5 + expand, y1 - lobe * 0.5 + expand),
            radius=int(lobe),
            fill=color,
        )


def _cloud_lobes(x0: float, y0: float, w: float, h: float, lobe: float) -> list[tuple[float, float, float]]:
    lobes: list[tuple[float, float, float]] = []
    steps = max(4, int(w / (lobe * 1.1)))
    for i in range(steps + 1):
        t = i / steps
        lobes.append((x0 + t * w, y0 + lobe * 0.55, lobe * (0.75 + 0.2 * math.sin(t * math.pi))))
        lobes.append((x0 + t * w, y0 + h - lobe * 0.55, lobe * (0.75 + 0.2 * math.cos(t * math.pi))))
    side_steps = max(2, int(h / (lobe * 1.2)))
    for i in range(side_steps + 1):
        t = i / side_steps
        lobes.append((x0 + lobe * 0.55, y0 + t * h, lobe * 0.7))
        lobes.append((x0 + w - lobe * 0.55, y0 + t * h, lobe * 0.7))
    return lobes


def _draw_burst(
    draw: ImageDraw.ImageDraw,
    rect: tuple[float, float, float, float],
    fill: tuple[int, int, int, int],
    outline: tuple[int, int, int, int],
    outline_w: int,
    *,
    spikes: int = 14,
    amplitude: float = 0.14,
) -> None:
    cx = (rect[0] + rect[2]) / 2
    cy = (rect[1] + rect[3]) / 2
    rx = (rect[2] - rect[0]) / 2
    ry = (rect[3] - rect[1]) / 2
    points: list[tuple[float, float]] = []
    peak = 1.0 + amplitude
    valley = 1.0 - amplitude * 1.3
    for i in range(spikes * 2):
        angle = math.pi * i / spikes
        if i % 2 == 0:
            radius_x, radius_y = rx * peak, ry * (peak + 0.04)
        else:
            radius_x, radius_y = rx * valley, ry * (valley - 0.02)
        points.append((cx + math.cos(angle) * radius_x, cy + math.sin(angle) * radius_y))
    draw.polygon(points, fill=fill, outline=outline)
    if outline_w > 1:
        draw.line(points + [points[0]], fill=outline, width=outline_w - 1)


def _draw_sfx(layer: Image.Image, sfx: SfxSpec, *, ink: tuple[int, int, int]) -> None:
    width, height = layer.size
    size = max(28, int(min(width, height) * 0.16 * max(0.4, min(sfx.scale, 2.0))))
    font = _sfx_font(size)
    probe = ImageDraw.Draw(layer)
    text_w = _text_width(probe, sfx.text, font)
    text_h = _line_height(probe, font)
    pad = max(10, size // 3)
    tile = Image.new("RGBA", (text_w + pad * 2, text_h + pad * 2), (0, 0, 0, 0))
    tile_draw = ImageDraw.Draw(tile)
    if sfx.style == "soft":
        main = (255, 255, 255, 235)
        stroke = (*ink, 200)
        stroke_w = max(2, size // 16)
    else:
        main = (*ink, 255)
        stroke = (255, 255, 255, 245)
        stroke_w = max(3, size // 10)
    tile_draw.text((pad, pad), sfx.text, font=font, fill=main, stroke_width=stroke_w, stroke_fill=stroke)
    if abs(sfx.angle) > 0.1:
        tile = tile.rotate(sfx.angle, expand=True, resample=Image.BICUBIC)
    px = int(sfx.anchor[0] * width - tile.width / 2)
    py = int(sfx.anchor[1] * height - tile.height / 2)
    px = max(-tile.width // 4, min(px, width - tile.width * 3 // 4))
    py = max(-tile.height // 4, min(py, height - tile.height * 3 // 4))
    layer.paste(tile, (px, py), tile)


def _strip_speaker_prefix(text: str) -> str:
    """Drop a leading `speaker：` label; the speaker is carried by the tail, not text."""
    for separator in ("：", ":"):
        head, mid, tail = text.partition(separator)
        if mid and head and len(head.strip()) <= 8 and tail.strip() and not any(char in _LINE_START_FORBIDDEN for char in head):
            return tail.strip()
    return text


def _wrap_cjk(draw: ImageDraw.ImageDraw, text: str, max_width: int, font: ImageFont.FreeTypeFont) -> list[str]:
    if max_width <= 0:
        return [text]
    lines: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        if current and _text_width(draw, candidate, font) > max_width:
            lines.append(current)
            current = char
        else:
            current = candidate
    if current:
        lines.append(current)
    return _apply_kinsoku(lines) or [text]


def _apply_kinsoku(lines: list[str]) -> list[str]:
    """CJK line-break rules: no forbidden char alone at a line start, none dangling at a line end."""
    adjusted = list(lines)
    for i in range(1, len(adjusted)):
        # Pull a forbidden leading char (。？！…) up to the previous line.
        while adjusted[i] and adjusted[i][0] in _LINE_START_FORBIDDEN:
            adjusted[i - 1] += adjusted[i][0]
            adjusted[i] = adjusted[i][1:]
        # Push a forbidden trailing char (「（ etc.) down to this line.
        while adjusted[i - 1] and adjusted[i - 1][-1] in _LINE_END_FORBIDDEN:
            adjusted[i] = adjusted[i - 1][-1] + adjusted[i]
            adjusted[i - 1] = adjusted[i - 1][:-1]
    return [line for line in adjusted if line]


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return int(bbox[2] - bbox[0])


def _line_height(draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont) -> int:
    bbox = draw.textbbox((0, 0), "国Ag", font=font)
    return int(bbox[3] - bbox[1])


def _clamp(value: float, low: float, high: float) -> float:
    if high < low:
        return (low + high) / 2
    return max(low, min(value, high))
