from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .project_layout import load_episode
from .story_gate import flatten_episode_panels
from .text_budget import validate_text_budget


class LetteringLayoutError(ValueError):
    pass


def validate_lettering_layout(
    project: str | Path,
    *,
    raise_on_fail: bool = True,
    write_report: bool = True,
) -> dict[str, Any]:
    root = Path(project)
    episode = load_episode(root)
    panels = flatten_episode_panels(episode)
    issues: list[dict[str, str]] = []
    try:
        budget_report = validate_text_budget(root, raise_on_fail=False, write_report=True)
        issues.extend({"code": item["code"], "path": item["path"], "message": item["message"]} for item in budget_report.get("issues", []))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        _issue(issues, "text-budget", "qa/text-budget-report.json", str(exc))
    card_overflow = 0
    for index, panel in enumerate(panels):
        panel_id = _text(panel.get("panel_id") or f"P{index + 1:02d}")
        variants = panel.get("text_variants")
        long_lines = _variant_lines(variants, "long_form") if isinstance(variants, Mapping) else []
        card_lines = _variant_lines(variants, "card_form") if isinstance(variants, Mapping) else []
        if long_lines == card_lines and long_lines:
            _issue(issues, "same-long-card-object", panel_id, "long_form and card_form must not be the same text.")
        if len(card_lines) > 3:
            card_overflow += 1
            _issue(issues, "card-paragraph-overflow", panel_id, "card_form must contain at most 3 paragraphs.")
        if any("..." in line or "…" in line for line in [*long_lines, *card_lines]):
            _issue(issues, "truncation-marker", panel_id, "Lettering must not silently truncate with ellipsis.")
        layout = panel.get("lettering_layout")
        if isinstance(layout, Mapping):
            min_font = layout.get("min_font_size")
            if isinstance(min_font, int) and min_font < 20:
                _issue(issues, "min-font-size", panel_id, "lettering_layout.min_font_size must be at least 20px.")
            if layout.get("safe_zone_collision") is True:
                _issue(issues, "safe-zone-collision", panel_id, "Text must not collide with panel safe zones.")
    report = {
        "schema_version": "3.0",
        "updated_at": _now(),
        "passed": not issues,
        "metrics": {
            "panel_count": len(panels),
            "card_overflow_panels": card_overflow,
            "minimum_font_size_px": 20,
        },
        "issues": issues,
    }
    if write_report:
        _write_json(root / "qa" / "lettering-layout-report.json", report)
    if raise_on_fail and issues:
        raise LetteringLayoutError("; ".join(item["message"] for item in issues))
    return report


def _issue(issues: list[dict[str, str]], code: str, path: str, message: str) -> None:
    issues.append({"code": code, "path": path, "message": message})


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _variant_lines(variants: Mapping[str, Any], key: str) -> list[str]:
    value = variants.get(key)
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    return []


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
