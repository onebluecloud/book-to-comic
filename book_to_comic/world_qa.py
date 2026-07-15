from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
import json
import re
from pathlib import Path
from typing import Any

from .world_model import load_world_model, world_model_sha256


SCHEMA_VERSION = "3.0"
GENERIC_WORDS = {
    "generic",
    "modern",
    "office",
    "room",
    "city",
    "street",
    "people",
    "background",
    "life scene",
    "ordinary",
    "一般",
    "普通",
    "现代",
    "办公室",
    "房间",
    "城市",
    "街道",
    "人群",
    "背景",
}


class WorldSpecificityError(ValueError):
    def __init__(self, message: str, report: dict[str, Any]):
        super().__init__(message)
        self.report = report


def validate_world_specificity(
    project: str | Path,
    *,
    against: list[str | Path] | None = None,
    raise_on_fail: bool = True,
    write_report: bool = True,
) -> dict[str, Any]:
    root = Path(project)
    world = load_world_model(root)
    env_bible = _load_optional_json(root / "planning" / "environment_bible.json")
    contract = _load_optional_json(root / "planning" / "visual_contract.json")
    issues: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    if str(world.get("planning_status", "")).strip() != "ready":
        _issue(issues, "planning-status", "planning/world_model.json.planning_status", "world_model.planning_status must be ready.")
    for field in ("era", "geography", "institutions", "material_culture", "access_rules"):
        if not _has_content(world.get(field)):
            _issue(issues, "world-field", f"planning/world_model.json.{field}", f"world_model.{field} is required.")
    environments = _environment_records(world, env_bible)
    if not environments:
        _issue(issues, "environments", "planning/world_model.json.environments", "world_model or environment_bible must define environments.")

    env_missing: dict[str, list[str]] = {}
    env_generic: dict[str, list[str]] = {}
    for env_id, env in environments.items():
        missing = [
            field
            for field in ("source_basis", "why_specific", "institutional_traces", "access_rules", "material_anchors", "functional_props")
            if not _has_content(env.get(field))
        ]
        if missing:
            env_missing[env_id] = missing
        generic = _generic_hits(_env_text(env))
        if generic:
            env_generic[env_id] = generic
    if env_missing:
        _issue(issues, "environment-specificity", "planning/world_model.json.environments[]", f"Environments missing specificity fields: {env_missing}.")
    root_generic_hits = _generic_hits(
        " ".join(
            [
                str(world.get("era") or ""),
                str(world.get("geography") or ""),
                _join(world.get("institutions")),
                _join(world.get("material_culture")),
                _join(world.get("access_rules")),
            ]
        )
    )
    if len(root_generic_hits) >= 3:
        _issue(issues, "generic-world-fields", "planning/world_model.json", f"Root world fields are generic: {root_generic_hits}.")
    generic_density = _generic_density(world, environments)
    if generic_density > 0.08:
        _issue(issues, "generic-density", "planning/world_model.json", f"Generic world-language density is too high: {generic_density:.3f}.")

    current_world_hash = world_model_sha256(root)
    contract_hash = ""
    if isinstance(contract.get("planning_hashes"), Mapping):
        contract_hash = str(contract["planning_hashes"].get("world_model_sha256") or "")
    visual_contract_world_hash_match = not contract_hash or contract_hash == current_world_hash
    if contract_hash and not visual_contract_world_hash_match:
        _issue(issues, "visual-contract-world-hash", "planning/visual_contract.json.planning_hashes.world_model_sha256", "visual_contract world_model_sha256 is stale.")

    collisions = _baseline_collisions(root, world, against or [])
    if collisions:
        _issue(warnings, "world-baseline-collision", "planning/world_model.json", f"World model shares signatures with baselines: {collisions}.")

    report = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": _now(),
        "passed": not issues,
        "metrics": {
            "environment_count": len(environments),
            "generic_density": round(generic_density, 4),
            "visual_contract_world_hash_match": visual_contract_world_hash_match,
            "world_model_sha256": current_world_hash,
        },
        "environment_missing": env_missing,
        "environment_generic_hits": env_generic,
        "root_generic_hits": root_generic_hits,
        "baseline_collisions": collisions,
        "issues": issues,
        "warnings": warnings,
    }
    if write_report:
        _write_json(root / "qa" / "world-specificity-report.json", report)
    if raise_on_fail and issues:
        raise WorldSpecificityError(f"World specificity failed with {len(issues)} issue(s)", report)
    return report


def _environment_records(world: Mapping[str, Any], env_bible: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for source in (world.get("environments"), env_bible.get("environments")):
        if not isinstance(source, list):
            continue
        for index, item in enumerate(source, start=1):
            if not isinstance(item, Mapping):
                continue
            env_id = str(item.get("id") or item.get("environment_id") or item.get("name") or f"ENV-{index:02d}").strip()
            if env_id:
                existing = dict(result.get(env_id, {}))
                existing.update(item)
                result[env_id] = existing
    return result


def _baseline_collisions(root: Path, world: Mapping[str, Any], against: list[str | Path]) -> list[str]:
    current = _world_signature(world)
    collisions: list[str] = []
    for item in against:
        other_root = Path(item)
        try:
            other = load_world_model(other_root)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
            continue
        if current and current == _world_signature(other):
            collisions.append(str(other_root))
    return collisions


def _world_signature(world: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        _norm(world.get("era")),
        _norm(world.get("geography")),
        _norm(world.get("institutions")),
    )


def _generic_density(world: Mapping[str, Any], environments: dict[str, Mapping[str, Any]]) -> float:
    text = _env_text(world) + " " + " ".join(_env_text(env) for env in environments.values())
    tokens = re.findall(r"[a-zA-Z]+(?: [a-zA-Z]+)?|[\u4e00-\u9fff]{2,4}", text.lower())
    if not tokens:
        return 0.0
    hits = sum(1 for token in tokens if token in GENERIC_WORDS)
    return hits / len(tokens)


def _generic_hits(text: str) -> list[str]:
    normalized = text.lower()
    return sorted({word for word in GENERIC_WORDS if word in normalized})


def _env_text(value: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for item in value.values():
        if isinstance(item, Mapping):
            parts.append(_env_text(item))
        elif isinstance(item, list):
            parts.extend(str(child) for child in item)
        else:
            parts.append(str(item))
    return " ".join(parts)


def _has_content(value: object) -> bool:
    if isinstance(value, Mapping):
        return any(_has_content(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_content(item) for item in value)
    return bool(str(value or "").strip())


def _join(value: object) -> str:
    if isinstance(value, list):
        return " ".join(str(item) for item in value if str(item).strip())
    if isinstance(value, Mapping):
        return " ".join(f"{key} {item}" for key, item in value.items() if str(item).strip())
    return str(value or "")


def _norm(value: object) -> str:
    if isinstance(value, list):
        return "|".join(str(item).strip().lower() for item in value if str(item).strip())
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _load_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _issue(target: list[dict[str, str]], code: str, path: str, message: str) -> None:
    target.append({"code": code, "path": path, "message": message})


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
