from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path
from typing import Any

from .schema_validation import require_valid_json_object


OFFICIAL_EPISODE_PATH = Path("story") / "episode-001.json"
LEGACY_EPISODE_PATH = Path("episodes") / "EP01" / "episode.json"
EPISODE_SCHEMA_VERSION = "3.0"


def episode_path(project: str | Path) -> Path:
    return Path(project) / OFFICIAL_EPISODE_PATH


def load_episode(project: str | Path) -> dict[str, Any]:
    path = episode_path(project)
    if not path.exists():
        raise FileNotFoundError(f"Official episode file is missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Official episode file must contain a JSON object: {path}")
    if "panels" in data:
        raise ValueError("Official episode JSON must not contain root panels[]; use scenes[].panels[].")
    # Fail closed at READ time for the current format: a hand-edited episode
    # with broken types used to surface as a confusing crash several stages
    # later (release audit P2-10). Legacy (pre-3.0) episodes keep the light
    # checks — the schema pins const 3.0 and would reject them wholesale.
    if str(data.get("schema_version") or "") == EPISODE_SCHEMA_VERSION:
        require_valid_json_object(data, "episode")
    return data


def save_episode(project: str | Path, episode: dict[str, Any]) -> Path:
    if not isinstance(episode, dict):
        raise ValueError("episode must be a JSON object")
    if "panels" in episode:
        raise ValueError("Official episode JSON must not contain root panels[]; use scenes[].panels[].")
    # Validate the in-memory object BEFORE touching the file, then write via a
    # same-directory temp file + os.replace. v5.12 overwrote first and
    # validated after (audit P1-2): a bad episode destroyed the good one and
    # left the schema-invalid version on disk.
    require_valid_json_object(episode, "episode")
    path = episode_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_text(json.dumps(episode, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp_path, path)
    return path


_EPISODE_ID_RE = re.compile(r"EP[0-9]{2,4}")


def validate_episode_id(episode_id: str) -> str:
    """The only accepted episode id shape wherever an id becomes a PATH.

    ``add-episode --episode ../escaped`` used to create a project outside the
    series directory, and host-image batch dirs escaped the project the same
    way (2026-07 release audit P1-1). EP + 2-4 digits, nothing else.
    """
    value = str(episode_id or "").strip()
    if not _EPISODE_ID_RE.fullmatch(value):
        raise ValueError(
            f"episode_id must be EP followed by 2-4 digits (EP01, EP012, ...): got {value!r}. "
            "No slashes, dots or other characters — episode ids become directory names."
        )
    return value


def declared_episode_id(episode: dict[str, Any]) -> str:
    return str(episode.get("episode_id") or "EP01").strip() or "EP01"


def resolve_episode_id(episode: dict[str, Any], requested: str | None) -> str:
    """The declared episode_id is the only truth; a mismatched request errors.

    v5.12 accepted any --episode label and stamped it onto this project's
    content (audit P0-3) — "EP02" prompts were EP01 prompts wearing a costume.
    One project holds exactly one episode; further episodes live in their own
    project directories (init-series / add-episode).
    """
    declared = declared_episode_id(episode)
    requested_id = (requested or "").strip()
    if requested_id and requested_id != declared:
        raise ValueError(
            f"This project's episode is {declared}; episode {requested_id!r} does not exist here. "
            "One project holds one episode — create the next episode as its own project with "
            "add-episode (series workflow) instead of relabeling this one."
        )
    return declared


def new_episode_skeleton(book_title: str, *, episode_id: str = "EP01") -> dict[str, Any]:
    return {
        "schema_version": EPISODE_SCHEMA_VERSION,
        "planning_status": "needs_host_planning",
        "episode_id": episode_id,
        "book_title": book_title,
        "episode_title": "",
        "primary_thesis": "",
        "source_refs": [],
        "style_id": "",
        "episode_format": "standard",
        "adaptation_strategy": {},
        "narrative_spine": {},
        "concept_units": [],
        "rhythm_plan": {},
        "story_ir": {},
        "scenes": [],
    }


def migrate_legacy_project(project: str | Path) -> dict[str, Any]:
    root = Path(project)
    official = episode_path(root)
    legacy = root / LEGACY_EPISODE_PATH
    if official.exists():
        return {
            "schema_version": EPISODE_SCHEMA_VERSION,
            "migrated": False,
            "reason": "official episode already exists",
            "episode_path": OFFICIAL_EPISODE_PATH.as_posix(),
        }
    if not legacy.exists():
        raise FileNotFoundError(f"Neither official nor legacy episode exists under {root}")

    data = json.loads(legacy.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Legacy episode file must contain a JSON object: {legacy}")
    migrated = _upgrade_legacy_episode(data)
    save_episode(root, migrated)
    return {
        "schema_version": EPISODE_SCHEMA_VERSION,
        "migrated": True,
        "migrated_from": LEGACY_EPISODE_PATH.as_posix(),
        "episode_path": OFFICIAL_EPISODE_PATH.as_posix(),
        "updated_at": _now(),
    }


def _upgrade_legacy_episode(data: dict[str, Any]) -> dict[str, Any]:
    book_title = str(data.get("book_title") or "")
    migrated = new_episode_skeleton(book_title, episode_id=str(data.get("episode_id") or "EP01"))
    for key in (
        "episode_title",
        "primary_thesis",
        "source_refs",
        "style_id",
        "adaptation_strategy",
        "narrative_spine",
        "story_ir",
        "scenes",
        "concept_units",
        "rhythm_plan",
    ):
        if key in data:
            migrated[key] = data[key]
    if data.get("planning_status"):
        migrated["planning_status"] = str(data["planning_status"])
    if not isinstance(migrated.get("scenes"), list):
        migrated["scenes"] = []
    legacy_panels = data.get("panels")
    if isinstance(legacy_panels, list) and legacy_panels and not migrated["scenes"]:
        migrated["legacy_migration"] = {
            "source": LEGACY_EPISODE_PATH.as_posix(),
            "status": "needs_host_replanning",
            "reason": "Legacy root panels were preserved as evidence only; official scenes[].panels[] must be replanned.",
            "panels": [panel for panel in legacy_panels if isinstance(panel, dict)],
        }
    return migrated


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
