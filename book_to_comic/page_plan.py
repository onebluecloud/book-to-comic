from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from .project_layout import load_episode
from .story_gate import flatten_episode_panels


SCHEMA_VERSION = "3.0"


def load_page_plan(project: str | Path) -> dict[str, Any]:
    episode = load_episode(project)
    plan = episode.get("page_plan")
    if not isinstance(plan, dict):
        plan = {}
    result = dict(plan)
    pages = episode.get("pages")
    if isinstance(pages, list):
        result["pages"] = pages
    if "planning_status" not in result:
        result["planning_status"] = str(episode.get("planning_status") or "")
    return result


def suggest_page_plan(project: str | Path, *, panels_per_page: int = 4) -> dict[str, Any]:
    if panels_per_page <= 0:
        raise ValueError("panels_per_page must be positive.")
    episode = load_episode(project)
    panels = [panel for panel in flatten_episode_panels(episode) if isinstance(panel, dict)]
    templates = ("three-beat", "one-plus-two", "two-plus-one")
    pages: list[dict[str, Any]] = []
    reading_order = 1
    for page_index, offset in enumerate(range(0, len(panels), panels_per_page), start=1):
        panel_ids: list[str] = []
        reading_orders: list[int] = []
        for slot_index, panel in enumerate(panels[offset : offset + panels_per_page], start=1):
            panel_id = str(panel.get("panel_id") or f"P{reading_order:02d}")
            panel_ids.append(panel_id)
            reading_orders.append(reading_order)
            role = str(panel.get("panel_role") or panel.get("story_function") or "action")
            reading_order += 1
        pages.append(
            {
                "page_id": f"PAGE-{page_index:02d}",
                "purpose": "setup" if page_index == 1 else "payoff" if offset + panels_per_page >= len(panels) else "escalation",
                "layout_template": templates[(page_index - 1) % len(templates)],
                "panel_ids": panel_ids,
                "focal_panel_id": panel_ids[0] if panel_ids else "",
                "reading_order": reading_orders,
                "rhythm": "balanced",
                "page_turn_reveal": page_index < (len(panels) + panels_per_page - 1) // panels_per_page,
                "gutter_policy": "normal",
                "text_flow": "caption-led",
                "why_this_layout": "Deterministic suggestion only; host must replace with a story-specific page rhythm before approval.",
                "lettering_anchor": "natural negative space",
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "planning_status": "needs_host_planning",
        "created_at": _now(),
        "pages": pages,
        "note": "Deterministic suggestion only; host must review and set planning_status=ready.",
    }


def page_plan_sha256(project: str | Path) -> str:
    try:
        plan = load_page_plan(project)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        return ""
    if not isinstance(plan.get("pages"), list) or not plan.get("pages"):
        return ""
    payload = json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def page_slots(page: Mapping[str, Any]) -> list[dict[str, Any]]:
    panel_ids = page.get("panel_ids")
    if not isinstance(panel_ids, list):
        slots = page.get("panel_slots")
        if isinstance(slots, list):
            return [dict(slot) for slot in slots if isinstance(slot, Mapping)]
        return []
    reading_order = page.get("reading_order")
    reading_orders = reading_order if isinstance(reading_order, list) else []
    result: list[dict[str, Any]] = []
    for index, panel_id in enumerate(panel_ids, start=1):
        order = reading_orders[index - 1] if index - 1 < len(reading_orders) else index
        result.append(
            {
                "slot_id": f"S{index}",
                "panel_id": str(panel_id),
                "reading_order": order,
                "focal_role": str(page.get("focal_role") or "action"),
                "lettering_anchor": str(page.get("lettering_anchor") or "natural negative space"),
                "layout_reason": str(page.get("why_this_layout") or page.get("layout_reason") or ""),
            }
        )
    return result


def panel_id(panel: Mapping[str, Any], fallback_index: int) -> str:
    return str(panel.get("panel_id") or f"P{fallback_index:02d}")


def _panel_lettering_anchor(panel: Mapping[str, Any]) -> str:
    zones = panel.get("caption_safe_zones")
    if isinstance(zones, list) and zones:
        return str(zones[0])
    anchor = panel.get("lettering_safe_zone")
    if str(anchor or "").strip():
        return str(anchor)
    return "natural negative space"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
