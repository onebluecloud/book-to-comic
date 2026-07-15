from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
import json
import re
from pathlib import Path
from typing import Any

from .character_design import validate_character_bible
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
    "appear",
    "appears",
    "看",
    "看着",
    "站",
    "站着",
    "坐",
    "坐着",
    "思考",
    "说明",
    "解释",
    "出现",
    "呈现",
}


class CharacterAgencyError(ValueError):
    def __init__(self, message: str, report: dict[str, Any]):
        super().__init__(message)
        self.report = report


def validate_character_design(
    project: str | Path,
    *,
    raise_on_fail: bool = True,
    write_report: bool = True,
) -> dict[str, Any]:
    root = Path(project)
    bible = _read_json(root / "planning" / "character_bible.json")
    episode = load_episode(root)
    panels = [panel for panel in flatten_episode_panels(episode) if isinstance(panel, dict)]
    issues: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    if str(bible.get("planning_status", "")).strip() != "ready":
        _issue(issues, "planning-status", "planning/character_bible.json.planning_status", "character_bible.planning_status must be ready.")
    if not str(bible.get("cast_model") or bible.get("role_architecture") or "").strip():
        _issue(issues, "cast-model", "planning/character_bible.json.cast_model", "A formal project needs a cast_model, not generic mascot roles.")

    try:
        base_report = validate_character_bible(root, raise_on_fail=False, write_report=False)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        base_report = {"passed": False, "issues": [{"code": "character-bible", "path": "planning/character_bible.json", "message": str(exc)}]}
    for item in base_report.get("issues", []):
        if isinstance(item, Mapping):
            _issue(issues, str(item.get("code") or "character-bible"), str(item.get("path") or "planning/character_bible.json"), str(item.get("message") or "Character bible issue."))

    characters = bible.get("characters")
    if not isinstance(characters, list) or not characters:
        _issue(issues, "characters", "planning/character_bible.json.characters", "characters must be a non-empty list.")
        characters = []
    char_ids = [_character_id(character, index) for index, character in enumerate(characters, start=1) if isinstance(character, Mapping)]
    protagonist_ids = [
        _character_id(character, index)
        for index, character in enumerate(characters, start=1)
        if isinstance(character, Mapping) and _looks_protagonist(character)
    ] or char_ids[:1]

    for index, character in enumerate(characters):
        if not isinstance(character, Mapping):
            continue
        char_id = _character_id(character, index + 1)
        agency = character.get("story_agency")
        if not isinstance(agency, Mapping):
            _issue(issues, "story-agency", f"characters[{index}].story_agency", f"{char_id} needs story_agency.")
            agency = {}
        for field in ("desire", "choice_pressure", "can_change_outcome", "visible_decisions"):
            if not _has_text(agency.get(field)):
                _issue(issues, "story-agency-field", f"characters[{index}].story_agency.{field}", f"{char_id}.story_agency.{field} is required.")
        if not _has_text(character.get("unremovable_reason")):
            _issue(issues, "unremovable", f"characters[{index}].unremovable_reason", f"{char_id} needs an unremovable story reason.")
        if not _has_text(character.get("shape_language")) or not _has_text(character.get("performance_design")):
            _issue(issues, "visual-performance", f"characters[{index}]", f"{char_id} needs shape_language and performance_design.")

    agency_counts = _panel_agency_counts(panels, char_ids)
    decision_counts = _decision_counts(panels, char_ids)
    passive_panels = [
        str(panel.get("panel_id") or f"P{index:02d}")
        for index, panel in enumerate(panels, start=1)
        if _is_passive_panel(panel)
    ]
    for char_id in protagonist_ids:
        if agency_counts.get(char_id, 0) < 2:
            _issue(issues, "protagonist-agency", "story/episode-001.json.scenes[].panels[]", f"{char_id} must visibly act in at least two panels.")
        if decision_counts.get(char_id, 0) < 1:
            _issue(issues, "protagonist-decision", "story/episode-001.json.scenes[].panels[]", f"{char_id} must make at least one visible decision.")
    if panels and len(passive_panels) / len(panels) > 0.45:
        _issue(issues, "passive-observer", "story/episode-001.json.scenes[].panels[]", "Too many panels are passive observation/explanation beats.")
    if len(char_ids) < 2:
        _issue(warnings, "small-cast", "planning/character_bible.json.characters", "Single-character episodes can pass only if page/action gates show enough agency.")

    report = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": _now(),
        "passed": not issues,
        "metrics": {
            "character_count": len(char_ids),
            "protagonist_ids": protagonist_ids,
            "panel_count": len(panels),
            "agency_counts": dict(agency_counts),
            "decision_counts": dict(decision_counts),
            "passive_panel_rate": round(len(passive_panels) / len(panels), 4) if panels else 0.0,
        },
        "passive_panels": passive_panels,
        "issues": issues,
        "warnings": warnings,
    }
    if write_report:
        _write_json(root / "qa" / "character-report.json", report)
    if raise_on_fail and issues:
        raise CharacterAgencyError(f"Character design failed with {len(issues)} issue(s)", report)
    return report


def export_character_prompts(project: str | Path, output_dir: str | Path | None = None) -> dict[str, Any]:
    root = Path(project)
    bible = _read_json(root / "planning" / "character_bible.json")
    final_dir = Path(output_dir) if output_dir else root / "prompts" / "characters"
    final_dir.mkdir(parents=True, exist_ok=True)
    prompts: list[dict[str, str]] = []
    characters = bible.get("characters") if isinstance(bible.get("characters"), list) else []
    for index, character in enumerate(characters, start=1):
        if not isinstance(character, Mapping):
            continue
        char_id = _character_id(character, index)
        path = final_dir / f"{char_id}.md"
        lines = [
            f"Character reference prompt: {char_id}",
            "Use this only for image generation of the character reference sheet.",
            "Do not render readable text, labels, speech bubbles, letters, numbers, UI, or pseudo-text.",
            f"Name: {character.get('name', '')}",
            f"Narrative role: {character.get('narrative_role') or character.get('role') or ''}",
            f"Story agency: {_flatten(character.get('story_agency'))}",
            f"Shape language: {character.get('shape_language', '')}",
            f"Face geometry: {character.get('face_geometry', '')}",
            f"Body design: {character.get('body_design', '')}",
            f"Wardrobe design: {character.get('wardrobe_design', '')}",
            f"Performance design: {_flatten(character.get('performance_design'))}",
        ]
        path.write_text("\n".join(line for line in lines if str(line).strip()) + "\n", encoding="utf-8")
        prompts.append({"character_id": char_id, "path": _rel(root, path)})
    manifest = {"schema_version": SCHEMA_VERSION, "prompt_type": "character-reference", "prompts": prompts}
    manifest_path = final_dir / "manifest.json"
    _write_json(manifest_path, manifest)
    return {"schema_version": SCHEMA_VERSION, "prompt_dir": str(final_dir), "manifest": str(manifest_path), "prompts": prompts}


def _panel_agency_counts(panels: list[dict[str, Any]], char_ids: list[str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for panel in panels:
        actors = _panel_actors(panel, char_ids)
        action = _action_verb(panel)
        if action and not _weak(action):
            for actor in actors:
                counts[actor] += 1
    return counts


def _decision_counts(panels: list[dict[str, Any]], char_ids: list[str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for panel in panels:
        initiative = panel.get("character_initiative")
        actor = ""
        if isinstance(initiative, Mapping):
            actor = str(initiative.get("actor") or initiative.get("character") or "").strip()
        actor = actor or str(panel.get("decision_maker") or panel.get("active_character") or "").strip()
        if actor in char_ids and (_has_text(panel.get("decision")) or _has_text(panel.get("choice")) or _has_text(initiative)):
            counts[actor] += 1
    return counts


def _panel_actors(panel: Mapping[str, Any], char_ids: list[str]) -> list[str]:
    result: list[str] = []
    for field in ("active_character", "decision_maker"):
        value = str(panel.get(field) or "").strip()
        if value in char_ids:
            result.append(value)
    initiative = panel.get("character_initiative")
    if isinstance(initiative, Mapping):
        value = str(initiative.get("actor") or initiative.get("character") or "").strip()
        if value in char_ids:
            result.append(value)
    present = panel.get("characters_present")
    if isinstance(present, list):
        result.extend(str(item).strip() for item in present if str(item).strip() in char_ids)
    return sorted(set(result))


def _is_passive_panel(panel: Mapping[str, Any]) -> bool:
    action = _action_verb(panel)
    if action and not _weak(action):
        return False
    if _has_text(panel.get("character_initiative")) or _has_text(panel.get("decision")) or _has_text(panel.get("observable_change")):
        return False
    text = " ".join(str(panel.get(field) or "") for field in ("action", "visual", "beat"))
    return not text or _weak(text)


def _action_verb(panel: Mapping[str, Any]) -> str:
    return str(panel.get("action_verb") or panel.get("action") or "").strip()


def _weak(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.lower()).strip()
    if not normalized:
        return True
    tokens = set(re.findall(r"[a-zA-Z]+|[\u4e00-\u9fff]{1,4}", normalized))
    return bool(tokens & WEAK_ACTIONS)


def _looks_protagonist(character: Mapping[str, Any]) -> bool:
    text = " ".join(str(character.get(field) or "") for field in ("id", "role", "narrative_role", "dramatic_function")).lower()
    return "protagonist" in text or "主角" in text or "主线" in text


def _character_id(character: Mapping[str, Any], fallback_index: int) -> str:
    return str(character.get("id") or character.get("name") or f"character-{fallback_index}").strip()


def _has_text(value: object) -> bool:
    if isinstance(value, Mapping):
        return any(_has_text(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_text(item) for item in value)
    return bool(str(value or "").strip())


def _flatten(value: object) -> str:
    if isinstance(value, Mapping):
        return "; ".join(f"{key}: {item}" for key, item in value.items() if _has_text(item))
    if isinstance(value, list):
        return "; ".join(str(item) for item in value if str(item).strip())
    return str(value or "")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required character design file is missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise CharacterAgencyError(f"character_bible must be a JSON object: {path}", {})
    return data


def _issue(target: list[dict[str, str]], code: str, path: str, message: str) -> None:
    target.append({"code": code, "path": path, "message": message})


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _rel(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
