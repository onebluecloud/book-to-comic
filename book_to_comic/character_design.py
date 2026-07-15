from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
import re
from pathlib import Path
from typing import Any


class CharacterDesignError(ValueError):
    pass


def validate_character_bible(
    project: str | Path,
    *,
    raise_on_fail: bool = True,
    write_report: bool = True,
) -> dict[str, Any]:
    root = Path(project)
    path = root / "planning" / "character_bible.json"
    issues: list[dict[str, str]] = []
    bible = _read_json(path)
    if str(bible.get("planning_status", "")).strip() != "ready":
        _issue(issues, "planning-status", "planning/character_bible.json.planning_status", "character_bible.planning_status must be ready.")
    characters = bible.get("characters")
    if not isinstance(characters, list) or not characters:
        _issue(issues, "characters", "planning/character_bible.json.characters", "characters must be a non-empty list.")
        characters = []

    required_text = (
        "id",
        "name",
        "narrative_role",
        "dramatic_function",
        "unremovable_reason",
        "appeal_strategy",
        "shape_language",
        "face_geometry",
        "body_design",
        "wardrobe_design",
    )
    for index, character in enumerate(characters):
        if not isinstance(character, Mapping):
            _issue(issues, "character-type", f"planning/character_bible.json.characters[{index}]", "Each character must be an object.")
            continue
        char_id = _text(character.get("id") or character.get("name") or f"character-{index + 1}")
        for field in required_text:
            if not _text(character.get(field)):
                _issue(issues, "character-field", f"characters[{index}].{field}", f"{field} is required for {char_id}.")
        if not _substantive_unremovable(character.get("unremovable_reason")):
            _issue(issues, "unremovable-reason", f"characters[{index}].unremovable_reason", "unremovable_reason must explain what story function breaks if removed.")
        performance = character.get("performance_design")
        if not isinstance(performance, Mapping) or not any(_text(value) for value in performance.values()):
            _issue(issues, "performance-design", f"characters[{index}].performance_design", "performance_design must include visible habits, gestures, posture, or motion.")
        engine = character.get("inner_engine")
        if not isinstance(engine, Mapping):
            _issue(issues, "inner-engine", f"characters[{index}].inner_engine", "inner_engine must include desire, fear, and choice_pressure.")
        else:
            for field in ("desire", "fear", "choice_pressure"):
                if not _text(engine.get(field)):
                    _issue(issues, "inner-engine", f"characters[{index}].inner_engine.{field}", f"inner_engine.{field} is required.")

    for left_index in range(len(characters)):
        left = characters[left_index]
        if not isinstance(left, Mapping):
            continue
        for right_index in range(left_index + 1, len(characters)):
            right = characters[right_index]
            if not isinstance(right, Mapping):
                continue
            if _looks_color_only_difference(left, right):
                _issue(
                    issues,
                    "color-only-difference",
                    "planning/character_bible.json.characters",
                    "Characters cannot differ only by color; shape, face, body, wardrobe structure and performance must diverge.",
                )

    relationships = bible.get("relationship_map")
    if not isinstance(relationships, list) or not relationships:
        _issue(issues, "relationship-map", "planning/character_bible.json.relationship_map", "relationship_map must be a non-empty list.")
    else:
        character_ids = {_text(item.get("id")) for item in characters if isinstance(item, Mapping)}
        for index, item in enumerate(relationships):
            if not isinstance(item, Mapping):
                _issue(issues, "relationship-map", f"relationship_map[{index}]", "Each relationship must be an object.")
                continue
            for field in ("from", "to", "relationship"):
                if not _text(item.get(field)):
                    _issue(issues, "relationship-map", f"relationship_map[{index}].{field}", f"{field} is required.")
            if character_ids and (_text(item.get("from")) not in character_ids or _text(item.get("to")) not in character_ids):
                _issue(issues, "relationship-map", f"relationship_map[{index}]", "relationship_map must reference existing character ids.")

    report = {
        "schema_version": "3.0",
        "updated_at": _now(),
        "passed": not issues,
        "metrics": {"character_count": len(characters), "relationship_count": len(relationships) if isinstance(relationships, list) else 0},
        "issues": issues,
    }
    if write_report:
        _write_json(root / "qa" / "character-bible-report.json", report)
    if raise_on_fail and issues:
        raise CharacterDesignError("; ".join(item["message"] for item in issues))
    return report


def _looks_color_only_difference(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    same_core = all(_norm(left.get(field)) == _norm(right.get(field)) for field in ("shape_language", "face_geometry", "body_design"))
    if not same_core:
        return False
    left_wardrobe = _norm_without_colors(left.get("wardrobe_design"))
    right_wardrobe = _norm_without_colors(right.get("wardrobe_design"))
    return left_wardrobe == right_wardrobe or _has_color_word(left.get("wardrobe_design")) or _has_color_word(right.get("wardrobe_design"))


def _substantive_unremovable(value: object) -> bool:
    text = _text(value)
    return len(text) >= 18 and any(token in text for token in ("删掉", "删除", "没有", "无法", "失去", "break", "remove"))


def _norm(value: object) -> str:
    return re.sub(r"\s+", " ", _text(value).lower()).strip()


def _norm_without_colors(value: object) -> str:
    text = _norm(value)
    colors = "red|blue|green|gray|grey|white|black|yellow|purple|orange|红|蓝|绿|灰|白|黑|黄|紫|橙"
    return re.sub(colors, "", text)


def _has_color_word(value: object) -> bool:
    return _norm_without_colors(value) != _norm(value)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required character bible is missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise CharacterDesignError(f"character_bible must be a JSON object: {path}")
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
