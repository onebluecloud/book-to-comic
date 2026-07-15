from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .project_layout import load_episode


SCHEMA_VERSION = "3.0"


class ArgumentMapError(ValueError):
    def __init__(self, message: str, report: dict[str, Any]):
        super().__init__(message)
        self.report = report


def load_argument_map(project: str | Path) -> dict[str, Any]:
    path = Path(project) / "planning" / "argument_map.json"
    if not path.exists():
        raise FileNotFoundError(f"Required argument map is missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ArgumentMapError("argument_map must be a JSON object.", {})
    return data


def selected_argument_ids(episode: Mapping[str, Any]) -> list[str]:
    plan = episode.get("knowledge_plan")
    candidates: list[Any] = []
    if isinstance(plan, Mapping):
        for key in ("selected_argument_ids", "selected_arguments", "argument_ids"):
            value = plan.get(key)
            if isinstance(value, list):
                candidates.extend(value)
    concept_units = episode.get("concept_units")
    if isinstance(concept_units, list):
        for item in concept_units:
            if isinstance(item, Mapping):
                value = item.get("argument_id")
                if value:
                    candidates.append(value)
    result: list[str] = []
    for item in candidates:
        if isinstance(item, Mapping):
            value = str(item.get("id") or item.get("argument_id") or "").strip()
        else:
            value = str(item).strip()
        if value and value not in result:
            result.append(value)
    return result


def validate_argument_map(
    project: str | Path,
    *,
    raise_on_fail: bool = True,
    write_report: bool = True,
) -> dict[str, Any]:
    root = Path(project)
    episode = load_episode(root)
    data = load_argument_map(root)
    issues: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    if str(data.get("planning_status", "")).strip() != "ready":
        _issue(issues, "planning-status", "planning/argument_map.json.planning_status", "argument_map.planning_status must be ready; missing planning must not be filled with generic defaults.")
    arguments = data.get("core_arguments")
    if not isinstance(arguments, list) or not arguments:
        _issue(issues, "core-arguments", "planning/argument_map.json.core_arguments", "core_arguments must be a non-empty list.")
        arguments = []
    argument_by_id: dict[str, Mapping[str, Any]] = {}
    approved = 0
    for index, argument in enumerate(arguments):
        if not isinstance(argument, Mapping):
            _issue(issues, "argument-type", f"core_arguments[{index}]", "Each core argument must be an object.")
            continue
        arg_id = str(argument.get("id") or f"ARG-{index + 1:02d}").strip()
        argument_by_id[arg_id] = argument
        for field in ("claim", "mechanism", "boundary", "adaptation_role"):
            if not _text(argument.get(field)):
                _issue(issues, "argument-field", f"core_arguments[{index}].{field}", f"{arg_id}.{field} is required.")
        if not _string_list(argument.get("source_refs")):
            _issue(issues, "argument-source-refs", f"core_arguments[{index}].source_refs", f"{arg_id} needs source_refs.")
        if str(argument.get("host_review_status") or "").strip() == "approved":
            approved += 1
        else:
            _issue(issues, "argument-review", f"core_arguments[{index}].host_review_status", f"{arg_id} must be host_review_status=approved.")

    selected = selected_argument_ids(episode)
    if not selected:
        _issue(issues, "selected-arguments", "story/episode-001.json.knowledge_plan.selected_argument_ids", "Episode must explicitly select arguments from planning/argument_map.json.")
    unknown = sorted(set(selected) - set(argument_by_id))
    if unknown:
        _issue(issues, "unknown-selected-arguments", "story/episode-001.json.knowledge_plan.selected_argument_ids", f"Unknown selected argument ids: {unknown}.")

    bridge_count = 0
    bridges = data.get("bridges")
    if isinstance(bridges, list):
        for index, bridge in enumerate(bridges):
            if not isinstance(bridge, Mapping):
                continue
            bridge_count += 1
            if not _text(bridge.get("simplification_note")):
                _issue(issues, "bridge-note", f"bridges[{index}].simplification_note", "Every bridge/simplification needs a simplification_note.")
            if not _string_list(bridge.get("source_refs")):
                _issue(issues, "bridge-source-refs", f"bridges[{index}].source_refs", "Every bridge needs source_refs.")
    else:
        _issue(warnings, "bridges", "planning/argument_map.json.bridges", "No argument bridges declared; acceptable only for very narrow chapters.")

    report = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": _now(),
        "passed": not issues,
        "metrics": {
            "core_argument_count": len(arguments),
            "approved_core_argument_count": approved,
            "selected_argument_count": len(selected),
            "bridge_count": bridge_count,
        },
        "selected_argument_ids": selected,
        "unknown_selected_argument_ids": unknown,
        "issues": issues,
        "warnings": warnings,
    }
    if write_report:
        _write_json(root / "qa" / "argument-map-report.json", report)
    if raise_on_fail and issues:
        raise ArgumentMapError(f"Argument map failed with {len(issues)} issue(s)", report)
    return report


def export_argument_planning_prompt(project: str | Path, output: str | Path | None = None) -> dict[str, Any]:
    root = Path(project)
    episode = load_episode(root)
    output_path = Path(output) if output else root / "prompts" / "planning" / "argument-map.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Argument Map Planning Prompt",
        "",
        "Build planning/argument_map.json for this episode. Do not invent source support.",
        "If the host cannot verify an argument, set planning_status to needs_host_planning.",
        "",
        f"Book: {episode.get('book_title', '')}",
        f"Episode: {episode.get('episode_title', '')}",
        f"Primary thesis: {episode.get('primary_thesis', '')}",
        "",
        "Required fields per core argument: id, claim, mechanism, boundary, source_refs, adaptation_role, host_review_status.",
        "Required bridge fields: id, from, to, simplification_note, source_refs.",
    ]
    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return {"schema_version": SCHEMA_VERSION, "prompt": str(output_path)}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _issue(target: list[dict[str, str]], code: str, path: str, message: str) -> None:
    target.append({"code": code, "path": path, "message": message})


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
