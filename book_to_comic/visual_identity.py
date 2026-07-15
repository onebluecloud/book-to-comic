from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "2.0"
PENDING_STATUS = "needs_host_planning"
READY_STATUS = "ready"
VISUAL_IDENTITY_RELATIVE_PATH = Path("planning") / "visual_identity.json"


class VisualIdentityError(ValueError):
    """Raised when a project visual identity is missing or not production-ready."""


def empty_visual_identity(book_title: str = "", style_id: str = "") -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "planning_status": PENDING_STATUS,
        "book_title": book_title,
        "style_id": style_id,
        "book_signature": {
            "book_type": "",
            "central_question": "",
            "source_era": "",
            "source_geography": "",
            "social_scale": "",
        },
        "adaptation_form": {
            "mode": "",
            "viewpoint": "",
            "why_specific_to_this_book": "",
        },
        "cast_model": {
            "role_architecture": "",
            "relationship_engine": "",
            "role_count": "",
        },
        "character_system": {
            "shape_language": "",
            "silhouette_rules": [],
            "body_variation": [],
            "wardrobe_rules": [],
            "archetype_bans": [],
        },
        "environment_system": {
            "era": "",
            "geography": "",
            "dominant_categories": [],
            "location_anchors": [],
            "recurring_layout_rules": [],
        },
        "motif_system": {
            "signature_props": [],
            "symbolic_motifs": [],
            "prop_state_rules": [],
        },
        "palette_lighting": {
            "palette": [],
            "lighting": "",
            "contrast_rules": "",
        },
        "camera_composition": {
            "opening_pattern": "",
            "panel_rhythm": "",
            "composition_rules": [],
        },
        "forbidden_carryover": [],
    }


def load_visual_identity(project: str | Path) -> dict[str, Any]:
    path = Path(project) / VISUAL_IDENTITY_RELATIVE_PATH
    if not path.exists():
        raise FileNotFoundError(f"Required visual identity is missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise VisualIdentityError(f"Visual identity must be a JSON object: {path}")
    return data


def validate_visual_identity(
    project: str | Path,
    *,
    raise_on_fail: bool = True,
    write_report: bool = True,
) -> dict[str, Any]:
    root = Path(project)
    errors: list[str] = []
    warnings: list[str] = []
    identity: dict[str, Any] = {}
    identity_hash = ""

    try:
        identity = load_visual_identity(root)
        identity_hash = visual_identity_sha256(identity)
    except (FileNotFoundError, OSError, json.JSONDecodeError, VisualIdentityError) as exc:
        errors.append(str(exc))

    if identity:
        status = str(identity.get("planning_status", "")).strip()
        if status == PENDING_STATUS:
            errors.append("visual_identity.planning_status is needs_host_planning")
        elif status != READY_STATUS:
            errors.append("visual_identity.planning_status must be ready")

        for path in _required_object_paths():
            value = _get(identity, path)
            if not isinstance(value, Mapping) or not value:
                errors.append(f"{_path_name(path)} must be a non-empty object")

        for path in _required_text_paths():
            value = _get(identity, path)
            if not str(value or "").strip():
                errors.append(f"{_path_name(path)} is required")

        for path in _required_list_paths():
            value = _get(identity, path)
            if not _string_list(value):
                errors.append(f"{_path_name(path)} must contain at least one item")

        why = str(_get(identity, ("adaptation_form", "why_specific_to_this_book")) or "").strip()
        if len(why) < 30:
            errors.append("adaptation_form.why_specific_to_this_book is too generic or too short")
        if _looks_generic_why(why):
            errors.append("adaptation_form.why_specific_to_this_book must explain why this book needs this visual form")

    passed = not errors
    report = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": _now(),
        "passed": passed,
        "status": "passed" if passed else "failed",
        "visual_identity_sha256": identity_hash,
        "summary": visual_identity_summary(identity) if identity else {},
        "metrics": {
            "required_object_count": len(_required_object_paths()),
            "required_text_count": len(_required_text_paths()),
            "required_list_count": len(_required_list_paths()),
        },
        "errors": errors,
        "warnings": warnings,
    }
    if write_report:
        _write_json(root / "qa" / "visual-identity-report.json", report)
    if raise_on_fail and not passed:
        raise VisualIdentityError("; ".join(errors) or "Visual identity validation failed.")
    return report


def visual_identity_sha256(project_or_identity: str | Path | Mapping[str, Any]) -> str:
    if isinstance(project_or_identity, Mapping):
        identity = dict(project_or_identity)
    else:
        identity = load_visual_identity(project_or_identity)
    encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def visual_identity_summary(identity: Mapping[str, Any]) -> dict[str, str]:
    return {
        "book_specificity": _join(_get(identity, ("book_signature",))),
        "adaptation_form": _join(_get(identity, ("adaptation_form",))),
        "cast_model": _join(_get(identity, ("cast_model",))),
        "character_shape_language": _join(_get(identity, ("character_system",))),
        "era_geography": _join(
            {
                "era": _get(identity, ("environment_system", "era")),
                "geography": _get(identity, ("environment_system", "geography")),
                "social_scale": _get(identity, ("book_signature", "social_scale")),
            }
        ),
        "environment_language": _join(_get(identity, ("environment_system",))),
        "signature_motifs": _join(_get(identity, ("motif_system",))),
        "palette_lighting": _join(_get(identity, ("palette_lighting",))),
        "camera_composition": _join(_get(identity, ("camera_composition",))),
        "forbidden_carryover": _join(identity.get("forbidden_carryover")),
    }


def _required_object_paths() -> list[tuple[str, ...]]:
    return [
        ("book_signature",),
        ("adaptation_form",),
        ("cast_model",),
        ("character_system",),
        ("environment_system",),
        ("motif_system",),
        ("palette_lighting",),
        ("camera_composition",),
    ]


def _required_text_paths() -> list[tuple[str, ...]]:
    return [
        ("book_title",),
        ("style_id",),
        ("book_signature", "book_type"),
        ("book_signature", "central_question"),
        ("book_signature", "source_era"),
        ("book_signature", "source_geography"),
        ("book_signature", "social_scale"),
        ("adaptation_form", "mode"),
        ("adaptation_form", "viewpoint"),
        ("adaptation_form", "why_specific_to_this_book"),
        ("cast_model", "role_architecture"),
        ("cast_model", "relationship_engine"),
        ("character_system", "shape_language"),
        ("environment_system", "era"),
        ("environment_system", "geography"),
        ("palette_lighting", "lighting"),
        ("camera_composition", "opening_pattern"),
        ("camera_composition", "panel_rhythm"),
    ]


def _required_list_paths() -> list[tuple[str, ...]]:
    return [
        ("character_system", "silhouette_rules"),
        ("character_system", "body_variation"),
        ("character_system", "wardrobe_rules"),
        ("environment_system", "dominant_categories"),
        ("environment_system", "location_anchors"),
        ("environment_system", "recurring_layout_rules"),
        ("motif_system", "signature_props"),
        ("motif_system", "symbolic_motifs"),
        ("motif_system", "prop_state_rules"),
        ("palette_lighting", "palette"),
        ("camera_composition", "composition_rules"),
        ("forbidden_carryover",),
    ]


def _looks_generic_why(text: str) -> bool:
    if not text:
        return True
    lowered = text.lower()
    generic = (
        "适合本书",
        "符合主题",
        "视觉化呈现",
        "让读者理解",
        "this book",
        "the theme",
        "generic",
        "tbd",
    )
    return any(item in lowered for item in generic) and len(text) < 80


def _get(value: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _join(value: object) -> str:
    if isinstance(value, Mapping):
        parts = []
        for key in sorted(value):
            text = _join(value[key])
            if text:
                parts.append(f"{key}: {text}")
        return "; ".join(parts)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "").strip()


def _path_name(path: tuple[str, ...]) -> str:
    return ".".join(path)


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
