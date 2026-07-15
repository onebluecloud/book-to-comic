from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


class EnvironmentDesignError(ValueError):
    pass


def validate_environment_bible(
    project: str | Path,
    *,
    raise_on_fail: bool = True,
    write_report: bool = True,
) -> dict[str, Any]:
    root = Path(project)
    bible = _read_json(root / "planning" / "environment_bible.json")
    issues: list[dict[str, str]] = []
    if str(bible.get("planning_status", "")).strip() != "ready":
        _issue(issues, "planning-status", "planning/environment_bible.json.planning_status", "environment_bible.planning_status must be ready.")
    system = bible.get("environment_system")
    if isinstance(system, Mapping):
        for field in ("era", "geography"):
            if not _text(system.get(field)):
                _issue(issues, "environment-system", f"environment_system.{field}", f"environment_system.{field} is required.")
        modes = system.get("grounding_modes")
        if not isinstance(modes, list) or not any(_text(item) for item in modes):
            _issue(issues, "grounding-modes", "environment_system.grounding_modes", "grounding_modes must list permitted grounding modes.")
    else:
        _issue(issues, "environment-system", "planning/environment_bible.json.environment_system", "environment_system is required.")

    environments = bible.get("environments")
    if not isinstance(environments, list) or not environments:
        _issue(issues, "environments", "planning/environment_bible.json.environments", "environments must be a non-empty list.")
        environments = []
    required_text = ("id", "name", "kind", "era", "geography", "lighting", "unremovable_reason")
    for index, environment in enumerate(environments):
        if not isinstance(environment, Mapping):
            _issue(issues, "environment-type", f"environments[{index}]", "Each environment must be an object.")
            continue
        for field in required_text:
            if not _text(environment.get(field)):
                _issue(issues, "environment-field", f"environments[{index}].{field}", f"{field} is required.")
        anchors = _string_list(environment.get("anchors"))
        if len(anchors) < 2:
            _issue(issues, "location-anchors", f"environments[{index}].anchors", "Each environment needs at least two visual anchors.")
        materials = _string_list(environment.get("material_palette"))
        if not materials:
            _issue(issues, "material-palette", f"environments[{index}].material_palette", "material_palette is required.")
        if not _substantive_unremovable(environment.get("unremovable_reason")):
            _issue(issues, "unremovable-reason", f"environments[{index}].unremovable_reason", "unremovable_reason must explain why the location cannot be removed.")

    report = {
        "schema_version": "3.0",
        "updated_at": _now(),
        "passed": not issues,
        "metrics": {"environment_count": len(environments)},
        "issues": issues,
    }
    if write_report:
        _write_json(root / "qa" / "environment-bible-report.json", report)
    if raise_on_fail and issues:
        raise EnvironmentDesignError("; ".join(item["message"] for item in issues))
    return report


def _substantive_unremovable(value: object) -> bool:
    text = _text(value)
    return len(text) >= 18 and any(token in text for token in ("删掉", "删除", "没有", "无法", "失去", "break", "remove"))


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    text = _text(value)
    return [text] if text else []


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required environment bible is missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise EnvironmentDesignError(f"environment_bible must be a JSON object: {path}")
    return data


def _issue(issues: list[dict[str, str]], code: str, path: str, message: str) -> None:
    issues.append({"code": code, "path": path, "message": message})


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
