from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .project_layout import load_episode
from .story_gate import flatten_episode_panels


class SourceClaimError(ValueError):
    pass


ALLOWED_GROUNDING_TYPES = {
    "contemporary_life",
    "historical_reconstruction",
    "institutional_process",
    "source_world",
    "material_detail",
    "analogy",
    "counterexample",
    "diagrammatic",
}
ALLOWED_FACTUALITY = {"source_fact", "source_interpretation", "source_based_reconstruction", "adaptation_bridge", "invented_bridge"}
SOURCE_BACKED_FACTUALITY = {"source_fact", "source_interpretation"}
HISTORICAL_BOOK_TYPES = {"history", "historical", "politics", "political", "institutional", "制度", "历史", "政治"}


def validate_source_claims(
    project: str | Path,
    *,
    raise_on_fail: bool = True,
    write_report: bool = True,
) -> dict[str, Any]:
    root = Path(project)
    episode = load_episode(root)
    issues: list[dict[str, str]] = []
    concept_units = episode.get("concept_units")
    if not isinstance(concept_units, list) or not concept_units:
        _issue(issues, "concept-units", "story/episode-001.json.concept_units", "concept_units must be a non-empty list.")
        concept_units = []
    concept_ids: set[str] = set()
    claim_source_supported = 0
    boundary_supported = 0
    invented_bridge_count = 0
    unsupported_claims: list[str] = []
    for index, unit in enumerate(concept_units):
        if not isinstance(unit, Mapping):
            _issue(issues, "concept-unit-type", f"concept_units[{index}]", "Each concept unit must be an object.")
            continue
        concept_id = _text(unit.get("concept_id") or unit.get("id"))
        if not concept_id:
            _issue(issues, "concept-id", f"concept_units[{index}].concept_id", "concept_id is required.")
        else:
            concept_ids.add(concept_id)
        for field in ("claim", "mechanism", "evidence", "boundary_conditions", "counterexample", "implication", "factuality"):
            if not _text(unit.get(field)):
                _issue(issues, "concept-field", f"concept_units[{index}].{field}", f"{field} is required.")
        refs = _string_list(unit.get("source_refs"))
        if not refs:
            _issue(issues, "concept-source-refs", f"concept_units[{index}].source_refs", "source_refs are required.")
        factuality = _text(unit.get("factuality"))
        if factuality in SOURCE_BACKED_FACTUALITY and refs:
            claim_source_supported += 1
        elif concept_id:
            unsupported_claims.append(concept_id)
        if _text(unit.get("boundary_conditions")):
            boundary_supported += 1
        if factuality in {"adaptation_bridge", "invented_bridge"} or any(ref.startswith(("invented_bridge", "adaptation_bridge")) for ref in refs):
            invented_bridge_count += 1
        if factuality in {"key_claim", "source_fact", "source_interpretation"} and refs and all(ref.startswith(("invented_bridge", "adaptation_bridge")) for ref in refs):
            _issue(issues, "invented-only-key-claim", f"concept_units[{index}].source_refs", "Key claims cannot be supported only by invented_bridge refs.")

    panels = flatten_episode_panels(episode)
    panels_with_anchor = 0
    grounding_type_counts: dict[str, int] = {}
    book_type = _book_type(root, episode)
    for scene_index, scene in enumerate(episode.get("scenes", [])):
        if not isinstance(scene, Mapping):
            continue
        scene_grounding = scene.get("grounding")
        if not isinstance(scene_grounding, Mapping):
            _issue(issues, "scene-grounding", f"scenes[{scene_index}].grounding", "Each scene needs grounding object; do not force every book into contemporary life_scene.")
        else:
            _validate_grounding(scene_grounding, f"scenes[{scene_index}].grounding", issues, grounding_type_counts)
        scene_concepts = set(_string_list(scene.get("concept_carried")))
        if concept_ids and not scene_concepts <= concept_ids:
            _issue(issues, "scene-concept-reference", f"scenes[{scene_index}].concept_carried", "Scene concept_carried references unknown concept unit.")
        for panel_index, panel in enumerate(scene.get("panels", []) if isinstance(scene.get("panels"), list) else []):
            if not isinstance(panel, Mapping):
                continue
            grounding = panel.get("grounding")
            if not isinstance(grounding, Mapping):
                _issue(issues, "panel-grounding", f"scenes[{scene_index}].panels[{panel_index}].grounding", "Each panel needs grounding object.")
            else:
                _validate_grounding(grounding, f"scenes[{scene_index}].panels[{panel_index}].grounding", issues, grounding_type_counts)
            anchors = panel.get("semantic_anchors")
            if not isinstance(anchors, list) or not anchors:
                _issue(issues, "semantic-anchors", f"scenes[{scene_index}].panels[{panel_index}].semantic_anchors", "Each panel needs semantic_anchors.")
                continue
            panel_anchor_ok = False
            for anchor_index, anchor in enumerate(anchors):
                if not isinstance(anchor, Mapping):
                    _issue(issues, "semantic-anchor-type", f"semantic_anchors[{anchor_index}]", "semantic anchor must be object.")
                    continue
                concept_id = _text(anchor.get("concept_id"))
                field = _text(anchor.get("field"))
                if concept_ids and concept_id not in concept_ids:
                    _issue(issues, "semantic-anchor-concept", f"semantic_anchors[{anchor_index}].concept_id", "semantic anchor references unknown concept unit.")
                if field not in {"claim", "mechanism", "evidence", "boundary_conditions", "counterexample", "implication"}:
                    _issue(issues, "semantic-anchor-field", f"semantic_anchors[{anchor_index}].field", "semantic anchor field must point to a concept unit field.")
                if concept_id in concept_ids and field:
                    panel_anchor_ok = True
            if panel_anchor_ok:
                panels_with_anchor += 1

    panel_count = len(panels)
    coverage = panels_with_anchor / panel_count if panel_count else 0.0
    if panel_count and coverage < 1.0:
        _issue(issues, "semantic-anchor-coverage", "story/episode-001.json.scenes[].panels[].semantic_anchors", "Every panel must map to a concept unit field.")
    contemporary_count = grounding_type_counts.get("contemporary_life", 0)
    grounded_count = sum(grounding_type_counts.values())
    if _is_historical_or_institutional(book_type) and grounded_count and contemporary_count == grounded_count:
        _issue(
            issues,
            "historical-grounding-mode",
            "story/episode-001.json.scenes[].panels[].grounding.type",
            "Historical, political, or institutional books cannot ground every panel as contemporary_life.",
        )
    report = {
        "schema_version": "3.0",
        "updated_at": _now(),
        "passed": not issues,
        "metrics": {
            "concept_unit_count": len(concept_units),
            "panel_count": panel_count,
            "concept_coverage": 1.0 if concept_units else 0.0,
            "claim_source_coverage": round(claim_source_supported / len(concept_units), 4) if concept_units else 0.0,
            "boundary_condition_coverage": round(boundary_supported / len(concept_units), 4) if concept_units else 0.0,
            "semantic_anchor_coverage": round(coverage, 4),
            "invented_bridge_count": invented_bridge_count,
            "grounding_type_counts": grounding_type_counts,
        },
        "unsupported_claims": unsupported_claims,
        "orphan_source_refs": [],
        "issues": issues,
    }
    if write_report:
        _write_json(root / "qa" / "source-claim-report.json", report)
    if raise_on_fail and issues:
        raise SourceClaimError("; ".join(item["message"] for item in issues))
    return report


def _validate_grounding(
    grounding: Mapping[str, Any],
    path: str,
    issues: list[dict[str, str]],
    counts: dict[str, int],
) -> None:
    grounding_type = _text(grounding.get("type") or grounding.get("mode"))
    if grounding_type not in ALLOWED_GROUNDING_TYPES:
        _issue(issues, "grounding-type", f"{path}.type", f"grounding.type must be one of {sorted(ALLOWED_GROUNDING_TYPES)}.")
    else:
        counts[grounding_type] = counts.get(grounding_type, 0) + 1
    for field in ("description", "why_this_mode", "factuality"):
        if not _text(grounding.get(field)):
            _issue(issues, "grounding-field", f"{path}.{field}", f"grounding.{field} is required.")
    factuality = _text(grounding.get("factuality"))
    if factuality and factuality not in ALLOWED_FACTUALITY:
        _issue(issues, "grounding-factuality", f"{path}.factuality", f"Unsupported grounding factuality `{factuality}`.")
    if factuality != "invented_bridge" and not _string_list(grounding.get("source_refs")):
        _issue(issues, "grounding-source-refs", f"{path}.source_refs", "source_refs are required unless grounding is explicitly invented_bridge.")


def _book_type(root: Path, episode: Mapping[str, Any]) -> str:
    explicit = _text(episode.get("book_type") or episode.get("source_type"))
    if explicit:
        return explicit
    path = root / "planning" / "visual_identity.json"
    if not path.exists():
        return ""
    try:
        identity = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(identity, Mapping):
        return ""
    signature = identity.get("book_signature")
    if isinstance(signature, Mapping):
        return _text(signature.get("book_type"))
    return ""


def _is_historical_or_institutional(book_type: str) -> bool:
    lowered = book_type.lower()
    return any(token in lowered for token in HISTORICAL_BOOK_TYPES)


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [_text(item) for item in value if _text(item)]
    text = _text(value)
    return [text] if text else []


def _issue(issues: list[dict[str, str]], code: str, path: str, message: str) -> None:
    issues.append({"code": code, "path": path, "message": message})


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
