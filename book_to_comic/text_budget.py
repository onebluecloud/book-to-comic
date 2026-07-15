from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
import re
from pathlib import Path
from typing import Any

from .project_layout import load_episode
from .story_gate import flatten_episode_panels


class TextBudgetError(ValueError):
    pass


def validate_text_budget(
    project: str | Path,
    *,
    raise_on_fail: bool = True,
    write_report: bool = True,
) -> dict[str, Any]:
    root = Path(project)
    episode = load_episode(root)
    panels = flatten_episode_panels(episode)
    issues: list[dict[str, str]] = []
    long_counts: list[int] = []
    card_counts: list[int] = []
    for index, panel in enumerate(panels):
        panel_id = _text(panel.get("panel_id") or f"P{index + 1:02d}")
        variants = panel.get("text_variants")
        if not isinstance(variants, Mapping):
            _issue(issues, "text-variants", panel_id, "text_variants with long_form and card_form is required.")
            continue
        long_lines = _variant_lines(variants, "long_form")
        card_lines = _variant_lines(variants, "card_form")
        long_count = _char_count(long_lines)
        card_count = _char_count(card_lines)
        long_counts.append(long_count)
        card_counts.append(card_count)
        if not long_lines:
            _issue(issues, "missing-long-form", panel_id, "long_form is required.")
        if not card_lines:
            _issue(issues, "missing-card-form", panel_id, "card_form is required.")
        if len(card_lines) > 3:
            _issue(issues, "card-paragraph-overflow", panel_id, "card_form must contain at most 3 paragraphs.")
        if card_lines and long_lines and card_lines == long_lines[: len(card_lines)]:
            _issue(issues, "card-sliced-from-long", panel_id, "card_form must be separately written, not sliced from long_form.")
        if _has_truncation_marker(long_lines + card_lines):
            _issue(issues, "truncation-marker", panel_id, "Text must not contain silent truncation markers or ellipsis.")
    panel_count = len(panels)
    avg_long = sum(long_counts) / panel_count if panel_count else 0.0
    avg_card = sum(card_counts) / panel_count if panel_count else 0.0
    from .text_qa import DEFAULT_THRESHOLDS

    avg_long_min = DEFAULT_THRESHOLDS["avg_long_min_chars"]
    if panel_count and avg_long < avg_long_min:
        _issue(issues, "avg-long-too-short", "episode", f"Average long_form length must be at least {avg_long_min} Chinese chars.")
    report = {
        "schema_version": "3.0",
        "updated_at": _now(),
        "passed": not issues,
        "metrics": {
            "panel_count": panel_count,
            "avg_long_chars": round(avg_long, 2),
            "avg_card_chars": round(avg_card, 2),
        },
        "issues": issues,
    }
    if write_report:
        _write_json(root / "qa" / "text-budget-report.json", report)
    if raise_on_fail and issues:
        raise TextBudgetError("; ".join(item["message"] for item in issues))
    return report


def _has_truncation_marker(lines: list[str]) -> bool:
    return any("..." in line or "…" in line for line in lines)


def _variant_lines(variants: Mapping[str, Any], key: str) -> list[str]:
    value = variants.get(key)
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    return []


def _char_count(lines: list[str]) -> int:
    return len(re.sub(r"\s+", "", "".join(lines)))


def _issue(issues: list[dict[str, str]], code: str, path: str, message: str) -> None:
    issues.append({"code": code, "path": path, "message": message})


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
