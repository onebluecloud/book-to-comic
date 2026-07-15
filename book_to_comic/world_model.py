from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "3.0"


class WorldModelError(ValueError):
    pass


def load_world_model(project: str | Path) -> dict[str, Any]:
    path = Path(project) / "planning" / "world_model.json"
    if not path.exists():
        raise FileNotFoundError(f"Required world model is missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise WorldModelError(f"world_model must be a JSON object: {path}")
    return data


def world_model_sha256(project: str | Path) -> str:
    try:
        data = load_world_model(project)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        return ""
    payload = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def export_environment_prompts(project: str | Path, output_dir: str | Path | None = None) -> dict[str, Any]:
    root = Path(project)
    world = load_world_model(root)
    env_bible = _load_optional_json(root / "planning" / "environment_bible.json")
    final_dir = Path(output_dir) if output_dir else root / "prompts" / "environments"
    final_dir.mkdir(parents=True, exist_ok=True)
    environments = _environment_records(world, env_bible)
    prompts: list[dict[str, str]] = []
    for env_id, env in environments.items():
        path = final_dir / f"{env_id}.md"
        lines = [
            f"Environment reference prompt: {env_id}",
            "Use this only for image generation of the environment reference sheet.",
            "Do not render readable text, labels, signage, UI, letters, numbers, or pseudo-text.",
            "World model lock:",
            f"- era: {world.get('era', '')}",
            f"- geography: {world.get('geography', '')}",
            f"- institutions: {_join(world.get('institutions'))}",
            f"- material culture: {_join(world.get('material_culture'))}",
            f"- access rules: {_join(world.get('access_rules'))}",
            f"Environment name: {env.get('name', '')}",
            f"Function in story: {env.get('function_in_story') or env.get('scene_function') or ''}",
            f"Specific anchors: {_join(env.get('anchors') or env.get('material_anchors'))}",
            f"Institutional traces: {_join(env.get('institutional_traces'))}",
            f"Source basis: {_join(env.get('source_basis'))}",
            f"Why specific: {env.get('why_specific', '')}",
        ]
        path.write_text("\n".join(line for line in lines if str(line).strip()) + "\n", encoding="utf-8")
        prompts.append({"environment_id": env_id, "path": _rel(root, path)})
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "prompt_type": "environment-reference",
        "world_model_sha256": world_model_sha256(root),
        "prompts": prompts,
    }
    manifest_path = final_dir / "manifest.json"
    _write_json(manifest_path, manifest)
    return {"schema_version": SCHEMA_VERSION, "prompt_dir": str(final_dir), "manifest": str(manifest_path), "prompts": prompts}


def _environment_records(world: Mapping[str, Any], env_bible: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for source in (world.get("environments"), env_bible.get("environments")):
        if not isinstance(source, list):
            continue
        for index, item in enumerate(source, start=1):
            if not isinstance(item, Mapping):
                continue
            env_id = str(item.get("id") or item.get("environment_id") or item.get("name") or f"ENV-{index:02d}").strip()
            if env_id and env_id not in result:
                result[env_id] = item
    return result


def _load_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _join(value: object) -> str:
    if isinstance(value, list):
        return "; ".join(str(item) for item in value if str(item).strip())
    if isinstance(value, Mapping):
        return "; ".join(f"{key}: {item}" for key, item in value.items() if str(item).strip())
    return str(value or "")


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
