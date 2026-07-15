from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .page_plan import load_page_plan, page_slots, panel_id
from .project_layout import load_episode
from .story_gate import flatten_episode_panels


SCHEMA_VERSION = "3.0"
FOCAL_ROLES = {"establishing", "action", "reaction", "turn", "insert", "payoff", "silent"}
LAYOUT_TEMPLATES = {"hero", "two-vertical", "three-beat", "four-grid", "one-plus-two", "two-plus-one", "full-bleed-inset"}
PAGE_PURPOSES = {"setup", "escalation", "crisis", "reveal", "payoff", "transition"}
PAGE_RHYTHMS = {"fast", "balanced", "held"}
TEXT_FLOWS = {"balloon-led", "caption-led", "mixed", "silent"}


class PagePlanError(ValueError):
    def __init__(self, message: str, report: dict[str, Any]):
        super().__init__(message)
        self.report = report


def validate_page_plan(
    project: str | Path,
    *,
    raise_on_fail: bool = True,
    write_report: bool = True,
) -> dict[str, Any]:
    root = Path(project)
    episode = load_episode(root)
    panels = [panel for panel in flatten_episode_panels(episode) if isinstance(panel, dict)]
    plan = load_page_plan(root)
    issues: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    if str(plan.get("planning_status", "")).strip() != "ready":
        _issue(issues, "planning-status", "story/episode-001.json.page_plan.planning_status", "page_plan.planning_status must be ready; deterministic suggestions are not final.")
    pages = plan.get("pages")
    if not isinstance(pages, list) or not pages:
        _issue(issues, "pages", "story/episode-001.json.pages", "pages[] or page_plan.pages[] is required for comic-page mode.")
        pages = []

    expected_ids = [panel_id(panel, index) for index, panel in enumerate(panels, start=1)]
    expected_set = set(expected_ids)
    assigned: list[str] = []
    reading_orders: list[int] = []
    template_counts: Counter[str] = Counter()
    single_panel_pages = 0
    invalid_slots: list[str] = []
    missing_layout_reason: list[str] = []
    missing_lettering_anchor: list[str] = []
    invalid_focal_role: list[str] = []
    formal_field_failures: list[str] = []

    for page_index, page in enumerate(pages, start=1):
        if not isinstance(page, Mapping):
            _issue(issues, "page-type", f"pages[{page_index - 1}]", "Each page must be an object.")
            continue
        page_id = str(page.get("page_id") or f"PAGE-{page_index:02d}")
        template = str(page.get("layout_template") or page.get("template") or "").strip()
        if not template:
            _issue(issues, "page-template", f"{page_id}.layout_template", "Each page needs a layout_template.")
        elif template not in LAYOUT_TEMPLATES:
            _issue(issues, "page-template", f"{page_id}.layout_template", f"layout_template must be one of {sorted(LAYOUT_TEMPLATES)}.")
        else:
            template_counts[template] += 1
        if str(page.get("purpose") or "").strip() not in PAGE_PURPOSES:
            _issue(issues, "page-purpose", f"{page_id}.purpose", f"purpose must be one of {sorted(PAGE_PURPOSES)}.")
        if str(page.get("rhythm") or "").strip() not in PAGE_RHYTHMS:
            _issue(issues, "page-rhythm", f"{page_id}.rhythm", f"rhythm must be one of {sorted(PAGE_RHYTHMS)}.")
        if str(page.get("text_flow") or "").strip() not in TEXT_FLOWS:
            _issue(issues, "page-text-flow", f"{page_id}.text_flow", f"text_flow must be one of {sorted(TEXT_FLOWS)}.")
        if not str(page.get("why_this_layout") or "").strip():
            _issue(issues, "page-layout-reason", f"{page_id}.why_this_layout", "Each page needs why_this_layout tied to narrative rhythm.")
        panel_ids_value = page.get("panel_ids")
        reading_order_value = page.get("reading_order")
        if not isinstance(panel_ids_value, list) or not panel_ids_value:
            formal_field_failures.append(f"{page_id}.panel_ids")
        if not isinstance(reading_order_value, list) or len(reading_order_value) != len(panel_ids_value if isinstance(panel_ids_value, list) else []):
            formal_field_failures.append(f"{page_id}.reading_order")
        focal_panel = str(page.get("focal_panel_id") or "").strip()
        if not focal_panel:
            formal_field_failures.append(f"{page_id}.focal_panel_id")
        elif isinstance(panel_ids_value, list) and focal_panel not in [str(item) for item in panel_ids_value]:
            _issue(issues, "focal-panel", f"{page_id}.focal_panel_id", "focal_panel_id must reference one of the page panel_ids.")
        slots = page_slots(page)
        if not slots:
            _issue(issues, "page-slots", f"{page_id}.panel_ids", "Each page needs formal panel_ids[].")
            continue
        if len(slots) == 1:
            single_panel_pages += 1
        for slot_index, slot in enumerate(slots, start=1):
            slot_path = f"{page_id}.panel_slots[{slot_index - 1}]"
            panel_ref = str(slot.get("panel_id") or "").strip()
            if not panel_ref:
                invalid_slots.append(slot_path)
                continue
            assigned.append(panel_ref)
            order = slot.get("reading_order")
            if isinstance(order, int):
                reading_orders.append(order)
            else:
                _issue(issues, "reading-order", f"{slot_path}.reading_order", "Each page slot needs integer reading_order.")
            focal_role = str(slot.get("focal_role") or "").strip()
            if focal_role not in FOCAL_ROLES:
                invalid_focal_role.append(f"{slot_path}.focal_role")
            if not str(slot.get("layout_reason") or "").strip():
                missing_layout_reason.append(slot_path)
            if not str(slot.get("lettering_anchor") or "").strip():
                missing_lettering_anchor.append(slot_path)

    duplicates = sorted(panel for panel, count in Counter(assigned).items() if count > 1)
    missing = sorted(expected_set - set(assigned))
    unknown = sorted(set(assigned) - expected_set)
    if invalid_slots:
        _issue(issues, "slot-panel-id", "pages[].panel_slots[].panel_id", "Each page slot must reference a panel_id.")
    if formal_field_failures:
        _issue(issues, "formal-page-fields", "pages[]", f"Formal comic-page fields are missing or invalid: {formal_field_failures}.")
    if missing:
        _issue(issues, "missing-panels", "pages[].panel_slots[].panel_id", f"Panels missing from page plan: {missing}.")
    if unknown:
        _issue(issues, "unknown-panels", "pages[].panel_slots[].panel_id", f"Page plan references unknown panels: {unknown}.")
    if duplicates:
        _issue(issues, "duplicate-panels", "pages[].panel_slots[].panel_id", f"Panels assigned more than once: {duplicates}.")
    if reading_orders and sorted(reading_orders) != list(range(1, len(reading_orders) + 1)):
        _issue(issues, "reading-order-sequence", "pages[].panel_slots[].reading_order", "reading_order must form one continuous sequence.")
    if invalid_focal_role:
        _issue(issues, "focal-role", "pages[].panel_slots[].focal_role", f"Invalid focal_role fields: {invalid_focal_role}.")
    if missing_layout_reason:
        _issue(issues, "layout-reason", "pages[].panel_slots[].layout_reason", "Every slot needs a concrete layout_reason tied to story rhythm.")
    if missing_lettering_anchor:
        _issue(issues, "lettering-anchor", "pages[].panel_slots[].lettering_anchor", "Every slot needs lettering_anchor so text is added after image generation.")

    page_count = len(pages)
    template_dominance = (template_counts.most_common(1)[0][1] / page_count) if page_count and template_counts else 0.0
    single_card_pattern_ratio = single_panel_pages / page_count if page_count else 0.0
    if page_count >= 3 and template_dominance > 0.7:
        _issue(issues, "template-repetition", "pages[].layout_template", "More than 70% of pages reuse the same layout_template.")
    if page_count >= 3 and single_card_pattern_ratio > 0.35:
        _issue(issues, "single-card-pattern", "pages[].panel_slots", "Too many pages are single-panel card patterns.")
    if len(panels) >= 5:
        role_counts = _panel_role_counts(panels)
        if role_counts.get("reaction", 0) < 1:
            _issue(issues, "reaction-beat", "story/episode-001.json.scenes[].panels[].panel_role", "At least one reaction beat is required for comic-page rhythm.")
        if role_counts.get("insert", 0) < 1:
            _issue(issues, "insert-beat", "story/episode-001.json.scenes[].panels[].panel_role", "At least one insert beat is required for comic-page rhythm.")
        if _silent_panel_count(panels) < 1:
            _issue(issues, "silent-beat", "story/episode-001.json.scenes[].panels[]", "At least one silent or low-text beat must be preserved for page pacing.")
    elif len(panels) < 5:
        _issue(warnings, "small-episode", "story/episode-001.json.scenes[].panels", "Panel count is too small to fully exercise reaction/insert/silent page rhythm.")

    report = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": _now(),
        "passed": not issues,
        "metrics": {
            "panel_count": len(panels),
            "page_count": page_count,
            "assigned_panel_count": len(assigned),
            "template_count": len(template_counts),
            "template_dominance": round(template_dominance, 4),
            "single_card_pattern_ratio": round(single_card_pattern_ratio, 4),
            "silent_panel_count": _silent_panel_count(panels),
            "role_counts": _panel_role_counts(panels),
        },
        "issues": issues,
        "warnings": warnings,
        "missing_panels": missing,
        "unknown_panels": unknown,
        "duplicate_panels": duplicates,
    }
    if write_report:
        _write_json(root / "qa" / "page-plan-report.json", report)
    if raise_on_fail and issues:
        raise PagePlanError(f"Page plan failed with {len(issues)} issue(s)", report)
    return report


def _panel_role_counts(panels: list[dict[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for panel in panels:
        role = str(panel.get("panel_role") or panel.get("story_function") or "").strip()
        if role:
            counts[role] += 1
    return dict(counts)


def _silent_panel_count(panels: list[dict[str, Any]]) -> int:
    count = 0
    for panel in panels:
        if panel.get("silent") is True:
            count += 1
            continue
        role = str(panel.get("panel_role") or panel.get("story_function") or "").strip()
        strategy = str(panel.get("text_strategy") or panel.get("beat_duration") or "").strip()
        if role == "silent" or "silent" in strategy or "pause" in strategy:
            count += 1
    return count


def _issue(target: list[dict[str, str]], code: str, path: str, message: str) -> None:
    target.append({"code": code, "path": path, "message": message})


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
