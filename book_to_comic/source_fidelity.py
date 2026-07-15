from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .argument_map import load_argument_map, selected_argument_ids
from .project_layout import load_episode
from .story_gate import flatten_episode_panels


SCHEMA_VERSION = "3.0"


class SourceFidelityError(ValueError):
    def __init__(self, message: str, report: dict[str, Any]):
        super().__init__(message)
        self.report = report


def validate_source_fidelity(
    project: str | Path,
    *,
    raise_on_fail: bool = True,
    write_report: bool = True,
) -> dict[str, Any]:
    root = Path(project)
    episode = load_episode(root)
    argument_map = load_argument_map(root)
    source_ids = _known_source_ids(root, episode)
    panels = [panel for panel in flatten_episode_panels(episode) if isinstance(panel, dict)]
    selected = selected_argument_ids(episode)
    argument_by_id = _argument_by_id(argument_map)
    selected_arguments = {arg_id: argument_by_id[arg_id] for arg_id in selected if arg_id in argument_by_id}
    issues: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    if not source_ids:
        _issue(issues, "source-chunks", "story/episode-001.json.story_ir.source_chunks", "story_ir.source_chunks or source/source_chunks.json is required for source fidelity.")
    if not selected:
        _issue(issues, "selected-arguments", "story/episode-001.json.knowledge_plan.selected_argument_ids", "Episode must explicitly select argument ids before fidelity review.")

    argument_panel_refs: defaultdict[str, list[str]] = defaultdict(list)
    unsupported_claim_panels: list[str] = []
    unknown_panel_arguments: dict[str, list[str]] = {}
    unknown_source_refs: dict[str, list[str]] = {}
    invented_without_note: list[str] = []
    for index, panel in enumerate(panels, start=1):
        panel_id = str(panel.get("panel_id") or f"P{index:02d}")
        refs = _string_list(panel.get("source_refs"))
        if source_ids:
            unknown_refs = sorted(set(refs) - source_ids)
            if unknown_refs:
                unknown_source_refs[panel_id] = unknown_refs
        if _looks_like_claim(panel) and not refs:
            unsupported_claim_panels.append(panel_id)
        arg_ids = _panel_argument_ids(panel)
        unknown_args = sorted(set(arg_ids) - set(argument_by_id))
        if unknown_args:
            unknown_panel_arguments[panel_id] = unknown_args
        for arg_id in arg_ids:
            if arg_id in argument_by_id:
                argument_panel_refs[arg_id].append(panel_id)
        if panel.get("invented_bridge") is True and not _text(panel.get("simplification_note")):
            invented_without_note.append(panel_id)

    if unknown_source_refs:
        _issue(issues, "unknown-source-refs", "story/episode-001.json.scenes[].panels[].source_refs", f"Panels reference unknown source chunks: {unknown_source_refs}.")
    if unknown_panel_arguments:
        _issue(issues, "unknown-panel-arguments", "story/episode-001.json.scenes[].panels[].argument_ids", f"Panels reference unknown arguments: {unknown_panel_arguments}.")
    if unsupported_claim_panels:
        _issue(issues, "unsupported-claims", "story/episode-001.json.scenes[].panels[]", f"Panels state claims without source_refs: {unsupported_claim_panels}.")
    if invented_without_note:
        _issue(issues, "invented-bridge-note", "story/episode-001.json.scenes[].panels[].simplification_note", f"Invented bridge panels need simplification_note: {invented_without_note}.")

    uncovered_selected: list[str] = []
    missing_mechanism: list[str] = []
    missing_boundary: list[str] = []
    missing_argument_source: list[str] = []
    unreviewed_core: list[str] = []
    argument_unknown_source_refs: dict[str, list[str]] = {}
    for arg_id, argument in selected_arguments.items():
        if not argument_panel_refs.get(arg_id):
            uncovered_selected.append(arg_id)
        if not _text(argument.get("mechanism")):
            missing_mechanism.append(arg_id)
        if not _text(argument.get("boundary")):
            missing_boundary.append(arg_id)
        refs = _string_list(argument.get("source_refs"))
        if not refs:
            missing_argument_source.append(arg_id)
        elif source_ids:
            unknown = sorted(set(refs) - source_ids)
            if unknown:
                argument_unknown_source_refs[arg_id] = unknown
        if str(argument.get("host_review_status") or "").strip() != "approved":
            unreviewed_core.append(arg_id)
    if uncovered_selected:
        _issue(issues, "selected-argument-coverage", "story/episode-001.json.scenes[].panels[].argument_ids", f"Selected arguments not used by any panel: {uncovered_selected}.")
    if missing_mechanism:
        _issue(issues, "mechanism-coverage", "planning/argument_map.json.core_arguments[].mechanism", f"Selected arguments missing mechanisms: {missing_mechanism}.")
    if missing_boundary:
        _issue(issues, "boundary-coverage", "planning/argument_map.json.core_arguments[].boundary", f"Selected arguments missing boundaries: {missing_boundary}.")
    if missing_argument_source:
        _issue(issues, "argument-source-coverage", "planning/argument_map.json.core_arguments[].source_refs", f"Selected arguments missing source_refs: {missing_argument_source}.")
    if argument_unknown_source_refs:
        _issue(issues, "argument-unknown-source-refs", "planning/argument_map.json.core_arguments[].source_refs", f"Arguments reference unknown source chunks: {argument_unknown_source_refs}.")
    if unreviewed_core:
        _issue(issues, "host-review", "planning/argument_map.json.core_arguments[].host_review_status", f"Selected arguments not approved: {unreviewed_core}.")

    selected_count = len(selected_arguments)
    report = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": _now(),
        "passed": not issues,
        "metrics": {
            "source_chunk_count": len(source_ids),
            "panel_count": len(panels),
            "selected_argument_count": selected_count,
            "selected_argument_panel_coverage": round((selected_count - len(uncovered_selected)) / selected_count, 4) if selected_count else 0.0,
            "mechanism_coverage": round((selected_count - len(missing_mechanism)) / selected_count, 4) if selected_count else 0.0,
            "boundary_coverage": round((selected_count - len(missing_boundary)) / selected_count, 4) if selected_count else 0.0,
            "panel_argument_counts": dict(Counter(arg_id for ids in [_panel_argument_ids(panel) for panel in panels] for arg_id in ids)),
        },
        "selected_argument_ids": selected,
        "uncovered_selected_argument_ids": uncovered_selected,
        "unsupported_claim_panels": unsupported_claim_panels,
        "unknown_source_refs": unknown_source_refs,
        "unknown_panel_arguments": unknown_panel_arguments,
        "invented_bridge_without_note": invented_without_note,
        "argument_unknown_source_refs": argument_unknown_source_refs,
        "issues": issues,
        "warnings": warnings,
    }
    if write_report:
        _write_json(root / "qa" / "source-fidelity-report.json", report)
    if raise_on_fail and issues:
        raise SourceFidelityError(f"Source fidelity failed with {len(issues)} issue(s)", report)
    return report


def _known_source_ids(root: Path, episode: Mapping[str, Any]) -> set[str]:
    ids: set[str] = set()
    story_ir = episode.get("story_ir")
    if isinstance(story_ir, Mapping):
        chunks = story_ir.get("source_chunks")
        if isinstance(chunks, list):
            ids.update(str(chunk.get("chunk_id") or "").strip() for chunk in chunks if isinstance(chunk, Mapping))
    source_path = root / "source" / "source_chunks.json"
    if source_path.exists():
        try:
            payload = json.loads(source_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        chunks = payload.get("chunks") if isinstance(payload, Mapping) else None
        if isinstance(chunks, list):
            ids.update(str(chunk.get("chunk_id") or "").strip() for chunk in chunks if isinstance(chunk, Mapping))
    return {item for item in ids if item}


def _argument_by_id(argument_map: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    arguments = argument_map.get("core_arguments")
    if not isinstance(arguments, list):
        return result
    for index, argument in enumerate(arguments, start=1):
        if not isinstance(argument, Mapping):
            continue
        arg_id = str(argument.get("id") or f"ARG-{index:02d}").strip()
        if arg_id:
            result[arg_id] = argument
    return result


def _panel_argument_ids(panel: Mapping[str, Any]) -> list[str]:
    result: list[str] = []
    for key in ("argument_ids", "selected_argument_ids", "concept_unit_ids"):
        value = panel.get(key)
        if isinstance(value, list):
            result.extend(str(item).strip() for item in value if str(item).strip())
    for key in ("argument_id", "concept_unit_id"):
        value = str(panel.get(key) or "").strip()
        if value:
            result.append(value)
    return sorted(set(result))


def _looks_like_claim(panel: Mapping[str, Any]) -> bool:
    for key in ("claim_text", "argument_claim", "narration", "connective_prose"):
        if _text(panel.get(key)):
            return True
    text_layers = panel.get("text_layers")
    if isinstance(text_layers, Mapping):
        return any(_text(text_layers.get(key)) for key in ("claim", "narration", "connective_prose", "long_form"))
    return False


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
