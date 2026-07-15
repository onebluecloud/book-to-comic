from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
import json
import re
from pathlib import Path
from typing import Any

from .project_layout import load_episode
from .story_gate import flatten_episode_panels


SCHEMA_VERSION = "3.0"
WEAK_ACTIONS = {
    "look",
    "looks",
    "see",
    "sees",
    "stand",
    "stands",
    "sit",
    "sits",
    "think",
    "thinks",
    "explain",
    "explains",
    "say",
    "says",
    "appear",
    "appears",
    "看",
    "看着",
    "站着",
    "坐着",
    "思考",
    "解释",
    "说明",
    "说",
    "出现",
    "呈现",
}


class ConflictGateError(ValueError):
    def __init__(self, message: str, report: dict[str, Any]):
        super().__init__(message)
        self.report = report


def validate_conflict(
    project: str | Path,
    *,
    raise_on_fail: bool = True,
    write_report: bool = True,
) -> dict[str, Any]:
    root = Path(project)
    episode = load_episode(root)
    issues: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    scenes = episode.get("scenes") if isinstance(episode.get("scenes"), list) else []
    panels = [panel for panel in flatten_episode_panels(episode) if isinstance(panel, dict)]

    spine = episode.get("narrative_spine")
    if not isinstance(spine, Mapping):
        _issue(issues, "narrative-spine", "story/episode-001.json.narrative_spine", "narrative_spine must be an object.")
        spine = {}
    for field in ("protagonist", "desire", "obstacle", "stakes", "escalation", "choice", "consequence", "this_episode_change"):
        if not _text(spine.get(field)):
            _issue(issues, "narrative-spine-field", f"narrative_spine.{field}", f"narrative_spine.{field} is required.")

    stakes_values: list[int] = []
    scene_missing: dict[str, list[str]] = {}
    for scene_index, scene in enumerate(scenes):
        if not isinstance(scene, Mapping):
            continue
        scene_id = str(scene.get("scene_id") or f"S{scene_index + 1:02d}")
        missing = [
            field
            for field in ("cause", "character_goal", "obstacle", "tactic", "setback", "decision", "consequence", "stakes")
            if not _text(scene.get(field))
        ]
        if missing:
            scene_missing[scene_id] = missing
        stakes = _int(scene.get("stakes_level"))
        if stakes is not None:
            stakes_values.append(stakes)
    if scene_missing:
        _issue(issues, "scene-conflict-fields", "story/episode-001.json.scenes[]", f"Scenes missing conflict fields: {scene_missing}.")

    weak_action_panels: list[str] = []
    missing_panel_contract: dict[str, list[str]] = {}
    no_change_panels: list[str] = []
    initiative_panels = 0
    for index, panel in enumerate(panels, start=1):
        panel_id = str(panel.get("panel_id") or f"P{index:02d}")
        missing = []
        for field in ("story_function", "cause", "effect", "observable_change"):
            if not _text(panel.get(field)):
                missing.append(field)
        initiative = panel.get("character_initiative")
        if isinstance(initiative, Mapping):
            if _text(initiative.get("actor")) and _text(initiative.get("action")):
                initiative_panels += 1
            else:
                missing.append("character_initiative.actor/action")
        elif not _text(panel.get("active_character")):
            missing.append("character_initiative")
        if missing:
            missing_panel_contract[panel_id] = missing
        action = _action(panel)
        if _weak(action):
            weak_action_panels.append(panel_id)
        if not _text(panel.get("observable_change")) and not _text(panel.get("effect")):
            no_change_panels.append(panel_id)
        stakes = _int(panel.get("stakes_level"))
        if stakes is not None:
            stakes_values.append(stakes)

    if missing_panel_contract:
        _issue(issues, "panel-conflict-contract", "story/episode-001.json.scenes[].panels[]", f"Panels missing conflict contract fields: {missing_panel_contract}.")
    panel_count = len(panels)
    weak_action_rate = len(weak_action_panels) / panel_count if panel_count else 0.0
    if panel_count and weak_action_rate > 0.35:
        _issue(issues, "weak-action-rate", "story/episode-001.json.scenes[].panels[].action_verb", "Too many panels use weak observation/explanation verbs instead of visible tactics.")
    if panel_count and initiative_panels / panel_count < 0.5:
        _issue(issues, "character-initiative-rate", "story/episode-001.json.scenes[].panels[].character_initiative", "At least half of panels need visible character initiative.")
    stakes_curve_passed = _stakes_curve_passed(stakes_values)
    if not stakes_curve_passed:
        _issue(issues, "stakes-curve", "story/episode-001.json.scenes[].stakes_level", "stakes_level must rise or turn; a flat sequence reads like a point list.")
    if len(set(_text(panel.get("story_function")) for panel in panels if _text(panel.get("story_function")))) < min(3, panel_count):
        _issue(warnings, "story-function-variety", "story/episode-001.json.scenes[].panels[].story_function", "Story functions are repetitive; review page rhythm.")

    report = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": _now(),
        "passed": not issues,
        "metrics": {
            "scene_count": len(scenes),
            "panel_count": panel_count,
            "weak_action_rate": round(weak_action_rate, 4),
            "character_initiative_rate": round(initiative_panels / panel_count, 4) if panel_count else 0.0,
            "stakes_curve": stakes_values,
            "stakes_curve_passed": stakes_curve_passed,
            "story_function_counts": dict(Counter(_text(panel.get("story_function")) for panel in panels if _text(panel.get("story_function")))),
        },
        "weak_action_panels": weak_action_panels,
        "no_change_panels": no_change_panels,
        "scene_missing": scene_missing,
        "missing_panel_contract": missing_panel_contract,
        "issues": issues,
        "warnings": warnings,
    }
    if write_report:
        _write_json(root / "qa" / "conflict-report.json", report)
    if raise_on_fail and issues:
        raise ConflictGateError(f"Conflict gate failed with {len(issues)} issue(s)", report)
    return report


def _stakes_curve_passed(values: list[int]) -> bool:
    if len(values) < 2:
        return False
    return max(values) > min(values) and values[-1] >= values[0]


def _action(panel: Mapping[str, Any]) -> str:
    return _text(panel.get("action_verb") or panel.get("action") or panel.get("visual"))


def _weak(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.lower()).strip()
    if not normalized:
        return True
    tokens = set(re.findall(r"[a-zA-Z]+|[\u4e00-\u9fff]{1,4}", normalized))
    return bool(tokens & WEAK_ACTIONS)


def _int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        text = str(value).strip()
        return int(text) if text else None
    except ValueError:
        return None


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _issue(target: list[dict[str, str]], code: str, path: str, message: str) -> None:
    target.append({"code": code, "path": path, "message": message})


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
