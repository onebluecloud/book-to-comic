from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .styles import list_showcase_style_ids


_REQUIRED_KEYS = {
    "schema_version",
    "style_id",
    "variant_id",
    "style_lock",
    "characters",
    "environments",
    "props",
    "color_script",
    "shot_plan",
    "lettering",
    "qa_gates",
}


def validate_art_bible(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    keys = set(data.keys())
    missing = _REQUIRED_KEYS - keys
    unknown = keys - _REQUIRED_KEYS
    if missing:
        errors.append(f"missing field(s): {', '.join(sorted(missing))}")
    if unknown:
        errors.append(f"unknown field(s): {', '.join(sorted(unknown))}")
    if data.get("style_id") not in list_showcase_style_ids():
        errors.append("style_id must be one of the nine stable style IDs")
    for field in ("characters", "environments", "props", "color_script", "shot_plan"):
        if field in data and not isinstance(data[field], list):
            errors.append(f"{field} must be a list")
    for field in ("style_lock", "lettering", "qa_gates"):
        if field in data and not isinstance(data[field], dict):
            errors.append(f"{field} must be an object")
    return errors


def read_art_bible(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    errors = validate_art_bible(data)
    if errors:
        raise ValueError("; ".join(errors))
    return data


def write_art_bible(path: str | Path, data: dict[str, Any]) -> Path:
    errors = validate_art_bible(data)
    if errors:
        raise ValueError("; ".join(errors))
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output
