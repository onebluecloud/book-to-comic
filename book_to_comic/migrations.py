from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .project_layout import LEGACY_EPISODE_PATH, OFFICIAL_EPISODE_PATH
from .text_pipeline import normalize_panel_text


SCHEMA_VERSION = "3.0"


class MigrationError(ValueError):
    pass


def migrate_project(project: str | Path, *, to_version: str = SCHEMA_VERSION) -> dict[str, Any]:
    if to_version != SCHEMA_VERSION:
        raise MigrationError(f"Unsupported target schema version: {to_version}")
    root = Path(project)
    episode_path = root / OFFICIAL_EPISODE_PATH
    legacy_path = root / LEGACY_EPISODE_PATH
    source_path = episode_path if episode_path.exists() else legacy_path
    if not source_path.exists():
        raise FileNotFoundError(f"No episode file found under {root}")
    raw = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise MigrationError(f"Episode must be a JSON object: {source_path}")

    migrated = dict(raw)
    migrated["schema_version"] = SCHEMA_VERSION
    migrated.pop("panels", None)
    actions: list[str] = []
    requires_host_planning = False

    legacy_panels = raw.get("panels")
    if isinstance(legacy_panels, list) and legacy_panels:
        migrated["legacy_migration"] = {
            "source": _rel(root, source_path),
            "status": "needs_host_planning",
            "reason": "Legacy root panels were preserved as evidence only; v3 requires scenes[].panels[] and pages[].",
            "panels": [panel for panel in legacy_panels if isinstance(panel, dict)],
        }
        actions.append("preserved legacy root panels under legacy_migration")
        requires_host_planning = True

    scenes = migrated.get("scenes")
    if not isinstance(scenes, list):
        migrated["scenes"] = []
        actions.append("created empty scenes[] for host planning")
        requires_host_planning = True
    else:
        migrated["scenes"] = _migrate_scenes(scenes)
        actions.append("normalized panel text into text_layers/text_variants")

    if not isinstance(migrated.get("knowledge_plan"), Mapping):
        migrated["knowledge_plan"] = {
            "planning_status": "needs_host_planning",
            "selected_argument_ids": [],
        }
        actions.append("created empty knowledge_plan")
        requires_host_planning = True

    if not isinstance(migrated.get("page_plan"), Mapping):
        migrated["page_plan"] = {
            "schema_version": SCHEMA_VERSION,
            "planning_status": "needs_host_planning",
            "pages": [],
        }
        actions.append("created empty page_plan")
        requires_host_planning = True

    planning_dir = root / "planning"
    planning_dir.mkdir(parents=True, exist_ok=True)
    planning_files = {
        "argument_map.json": _argument_map_stub(migrated),
        "world_model.json": _world_model_stub(migrated),
    }
    created_planning_files: list[str] = []
    for filename, stub in planning_files.items():
        path = planning_dir / filename
        if not path.exists():
            _write_json(path, stub)
            created_planning_files.append(f"planning/{filename}")
            requires_host_planning = True
    if created_planning_files:
        actions.append(f"created planning stubs: {created_planning_files}")

    if requires_host_planning:
        migrated["planning_status"] = "needs_host_planning"
    elif not str(migrated.get("planning_status") or "").strip():
        migrated["planning_status"] = "needs_host_planning"
        requires_host_planning = True

    _write_json(episode_path, migrated)
    report = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": _now(),
        "migrated": True,
        "from": _rel(root, source_path),
        "to": OFFICIAL_EPISODE_PATH.as_posix(),
        "planning_status": migrated.get("planning_status"),
        "requires_host_planning": requires_host_planning,
        "created_planning_files": created_planning_files,
        "actions": actions,
    }
    _write_json(root / "qa" / "migration-report.json", report)
    return report


def _migrate_scenes(scenes: list[Any]) -> list[Any]:
    migrated_scenes: list[Any] = []
    for scene in scenes:
        if not isinstance(scene, dict):
            migrated_scenes.append(scene)
            continue
        updated_scene = dict(scene)
        panels = scene.get("panels")
        if isinstance(panels, list):
            updated_scene["panels"] = [normalize_panel_text(panel) if isinstance(panel, dict) else panel for panel in panels]
        migrated_scenes.append(updated_scene)
    return migrated_scenes


def _argument_map_stub(episode: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "planning_status": "needs_host_planning",
        "book_title": str(episode.get("book_title") or ""),
        "episode_id": str(episode.get("episode_id") or "EP01"),
        "core_arguments": [],
        "bridges": [],
        "required_host_checks": [
            "Extract source-backed claims.",
            "Write mechanism and boundary for each core argument.",
            "Approve selected arguments before image planning.",
        ],
    }


def _world_model_stub(episode: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "planning_status": "needs_host_planning",
        "book_title": str(episode.get("book_title") or ""),
        "episode_id": str(episode.get("episode_id") or "EP01"),
        "era": "",
        "geography": "",
        "institutions": [],
        "material_culture": [],
        "access_rules": [],
        "environments": [],
        "required_host_checks": [
            "Anchor the world in source-backed era/geography/institutions.",
            "Define material culture, access rules, traces, and functional props.",
        ],
    }


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
