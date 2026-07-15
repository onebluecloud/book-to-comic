"""Deterministic balloon auto-placement.

The host VLM stays in the jobs it is good at — transcribing dialogue, marking
who speaks from where (``anchor``), and boxing the untouchable regions
(``no_go_boxes``). This module takes over the job VLMs are bad at: choosing
exact box coordinates. Balloons are placed one at a time in reading order; each
candidate position must clear every hard constraint the validator enforces
(face/subject no-go, balloon overlap, reading precedence), then the cheapest
candidate wins an energy score built from the professional placement priors:
above the speaker beats corners beats edges beats bottom, short natural tails
beat long ones.

Same math as ``validate_balloon_plan`` — the validator rejects what this module
would never emit, so auto-placed plans validate by construction.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .balloons import (
    FACE_OVERLAP_LIMIT,
    MAX_BALLOON_AREA_RATIO,
    MIN_BALLOON_GAP,
    SUBJECT_OVERLAP_LIMIT,
    BalloonSpec,
    NoGoBox,
    balloon_plan_path,
    box_gap,
    box_overlap_ratio,
    estimate_balloon_box,
    precedence_violations,
)

GRID_STEPS = 22
EDGE_MARGIN = 0.02


def place_balloons_for_panel(
    balloons: list[dict[str, Any]],
    no_go_boxes: list[dict[str, Any]],
    panel_size: tuple[int, int],
    writing_mode: str = "horizontal",
) -> list[dict[str, Any] | None]:
    """Compute a box for every balloon dict lacking one.

    Returns one entry per input balloon: the placed box as ``{x, y, w, h}``, or
    None when the balloon already had a box (untouched) or no legal position
    exists (caller should split the text or fall back to a caption).
    """
    no_go = [
        NoGoBox(
            box=(float(item.get("x", 0)), float(item.get("y", 0)), float(item.get("w", 0)), float(item.get("h", 0))),
            label=str(item.get("label") or ""),
        )
        for item in no_go_boxes
    ]
    placed_specs: list[BalloonSpec] = []
    results: list[dict[str, Any] | None] = []

    ordered = sorted(range(len(balloons)), key=lambda i: int(balloons[i].get("reading_order") or (i + 1)))
    boxes_out: dict[int, dict[str, Any] | None] = {}

    for index in ordered:
        item = balloons[index]
        anchor = item.get("anchor") or {}
        anchor_pt = (float(anchor.get("x", 0.5)), float(anchor.get("y", 0.5)))
        existing = item.get("box")
        if isinstance(existing, dict) and existing.get("w"):
            boxes_out[index] = None
            placed_specs.append(_spec(item, existing, anchor_pt))
            continue
        estimate = estimate_balloon_box(str(item.get("text") or ""), panel_size, writing_mode)
        if estimate["split_required"]:
            boxes_out[index] = None
            continue
        best = _best_position(
            (estimate["box_w"], estimate["box_h"]),
            anchor_pt,
            no_go,
            placed_specs,
            item,
            writing_mode,
        )
        if best is None:
            boxes_out[index] = None
            continue
        box = {"x": best[0], "y": best[1], "w": estimate["box_w"], "h": estimate["box_h"]}
        boxes_out[index] = box
        placed_specs.append(_spec(item, box, anchor_pt))

    for i in range(len(balloons)):
        results.append(boxes_out.get(i))
    return results


def _spec(item: dict[str, Any], box: dict[str, Any], anchor_pt: tuple[float, float]) -> BalloonSpec:
    return BalloonSpec(
        balloon_id=str(item.get("balloon_id") or "B"),
        kind=str(item.get("type") or "speech"),
        text=str(item.get("text") or ""),
        speaker=str(item.get("speaker") or ""),
        anchor=anchor_pt,
        box=(float(box["x"]), float(box["y"]), float(box["w"]), float(box["h"])),
        tail=bool(item.get("tail", True)),
        reading_order=int(item.get("reading_order") or 1),
    )


def _best_position(
    box_wh: tuple[float, float],
    anchor: tuple[float, float],
    no_go: list[NoGoBox],
    placed: list[BalloonSpec],
    item: dict[str, Any],
    writing_mode: str,
) -> tuple[float, float] | None:
    bw, bh = box_wh
    if bw * bh > MAX_BALLOON_AREA_RATIO or bw >= 1.0 or bh >= 1.0:
        return None
    best: tuple[float, tuple[float, float]] | None = None
    span_x = 1.0 - bw - 2 * EDGE_MARGIN
    span_y = 1.0 - bh - 2 * EDGE_MARGIN
    if span_x <= 0 or span_y <= 0:
        return None
    for iy in range(GRID_STEPS + 1):
        y = EDGE_MARGIN + span_y * iy / GRID_STEPS
        for ix in range(GRID_STEPS + 1):
            x = EDGE_MARGIN + span_x * ix / GRID_STEPS
            candidate = (x, y, bw, bh)
            if _violates_hard_constraints(candidate, no_go, placed, item, anchor, writing_mode):
                continue
            energy = _energy(candidate, anchor)
            if best is None or energy < best[0]:
                best = (energy, (round(x, 3), round(y, 3)))
    return best[1] if best else None


def _violates_hard_constraints(
    candidate: tuple[float, float, float, float],
    no_go: list[NoGoBox],
    placed: list[BalloonSpec],
    item: dict[str, Any],
    anchor: tuple[float, float],
    writing_mode: str,
) -> bool:
    for region in no_go:
        limit = FACE_OVERLAP_LIMIT if region.is_face else SUBJECT_OVERLAP_LIMIT
        if box_overlap_ratio(candidate, region.box) > limit + 1e-9:
            return True
    for spec in placed:
        if box_overlap_ratio(candidate, spec.box) > 0 or box_gap(candidate, spec.box) < MIN_BALLOON_GAP:
            return True
    # anchor must stay outside the balloon core so the tail keeps direction
    cx0 = candidate[0] + candidate[2] * 0.30
    cx1 = candidate[0] + candidate[2] * 0.70
    cy0 = candidate[1] + candidate[3] * 0.30
    cy1 = candidate[1] + candidate[3] * 0.70
    if cx0 <= anchor[0] <= cx1 and cy0 <= anchor[1] <= cy1:
        return True
    if placed:
        trial = list(placed) + [_spec(item, {"x": candidate[0], "y": candidate[1], "w": candidate[2], "h": candidate[3]}, anchor)]
        if precedence_violations(trial, writing_mode):
            return True
    return False


def _energy(candidate: tuple[float, float, float, float], anchor: tuple[float, float]) -> float:
    """Professional priors, lower is better: above the speaker, near a corner,
    short tail, never crammed at the bottom."""
    x, y, w, h = candidate
    cx, cy = x + w / 2, y + h / 2
    tail_len = math.hypot(cx - anchor[0], cy - anchor[1])
    above_bonus = 0.0 if cy < anchor[1] else 0.45          # prefer above the speaker
    vertical_prior = cy * 0.9                              # higher on the panel is calmer
    same_side_penalty = 0.15 if (cx - 0.5) * (anchor[0] - 0.5) < 0 else 0.0
    tail_penalty = abs(tail_len - 0.28) * 1.2              # natural tail ~ a quarter panel
    return vertical_prior + above_bonus + same_side_penalty + tail_penalty


def auto_place_project(project: str | Path, *, force: bool = False) -> dict[str, Any]:
    """Fill in missing balloon boxes across a project's balloon plan, in place.

    Only balloons without a ``box`` key are placed (``force=True`` replaces all).
    Returns a summary; the host reviews the result and runs validate-balloon-plan.
    """
    root = Path(project)
    path = balloon_plan_path(root)
    if not path.is_file():
        raise FileNotFoundError(f"Balloon plan not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    writing_mode = str(payload.get("writing_mode") or "horizontal")
    placed_count = 0
    unplaced: list[str] = []
    for panel in payload.get("panels", []):
        balloons = panel.get("balloons") or []
        if force:
            for balloon in balloons:
                balloon.pop("box", None)
        pending = [b for b in balloons if "box" not in b]
        if not pending:
            continue
        panel_size = (int(panel.get("panel_width") or 1536), int(panel.get("panel_height") or 1024))
        boxes = place_balloons_for_panel(balloons, panel.get("no_go_boxes") or [], panel_size, writing_mode)
        for balloon, box in zip(balloons, boxes):
            if "box" in balloon:
                continue
            if box is None:
                unplaced.append(f"{panel.get('panel_id')}:{balloon.get('balloon_id') or balloon.get('text', '')[:10]}")
            else:
                balloon["box"] = box
                placed_count += 1
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return {
        "placed": placed_count,
        "unplaced": unplaced,
        "note": "unplaced balloons need shorter text (split) or a caption fallback",
    }
