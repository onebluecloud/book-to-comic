from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .page_plan import page_plan_sha256
from .project_layout import load_episode
from .visual_distinctiveness import validate_distinctiveness
from .visual_identity import load_visual_identity, validate_visual_identity, visual_identity_sha256, visual_identity_summary
from .world_model import world_model_sha256


SCHEMA_VERSION = "2.0"


def build_visual_contract(project: str | Path) -> dict[str, Any]:
    root = Path(project)
    identity_report = validate_visual_identity(root)
    distinctiveness_report = _ensure_distinctiveness_report(root)
    visual_identity = load_visual_identity(root)
    identity_hash = str(identity_report.get("visual_identity_sha256") or visual_identity_sha256(visual_identity))
    episode = load_episode(root)
    character_bible = _read_json(root / "planning" / "character_bible.json")
    environment_bible = _read_json(root / "planning" / "environment_bible.json")
    planning_hashes = _planning_hashes(root)

    character_records = _character_records(character_bible)
    environment_records = _environment_records(environment_bible)
    character_aliases = _character_aliases(character_records)
    environment_aliases = _environment_aliases(environment_records)
    panel_contexts = _panel_contexts(episode, environment_aliases)
    prop_ids = _episode_prop_ids(panel_contexts, character_records)

    character_state = _build_character_state(panel_contexts, character_records, character_aliases)
    environment_state = _build_environment_state(panel_contexts, environment_records)
    prop_state = _build_prop_state(panel_contexts, prop_ids)
    panel_locks = _build_panel_locks(panel_contexts, character_records, character_aliases, environment_aliases)
    reference_pack = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": _now(),
        "visual_identity_summary": visual_identity_summary(visual_identity),
        "visual_identity_sha256": identity_hash,
        "planning_hashes": planning_hashes,
        "world_model_summary": _world_model_summary(root),
        "distinctiveness_status": _distinctiveness_status(distinctiveness_report),
        "characters": {
            char_id: {
                "name": str(record.get("name", "")),
                "role": str(record.get("role", "")),
                "visual": str(record.get("visual", "")),
                "prompt_fragment": str(record.get("prompt_fragment", "")),
                "wardrobe_lock": _lock_value(record.get("wardrobe_lock")),
                "prop_lock": _lock_value(record.get("prop_lock")),
            }
            for char_id, record in character_records.items()
        },
        "environments": {
            env_id: {
                "name": str(record.get("name", "")),
                "kind": str(record.get("kind", "")),
                "anchors": _string_list(record.get("anchors")),
            }
            for env_id, record in environment_records.items()
        },
        "props": {
            prop_id: {
                "description": prop_state[prop_id]["description"],
                "first_state": prop_state[prop_id]["states"][0] if prop_state[prop_id]["states"] else "",
                "panel_ids": prop_state[prop_id]["panel_ids"],
            }
            for prop_id in sorted(prop_state)
        },
        "panel_locks": panel_locks,
    }
    contract = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": _now(),
        "episode_id": str(episode.get("episode_id", "EP01")),
        "book_title": str(episode.get("book_title", "")),
        "style_id": str(episode.get("style_id", "")),
        "visual_identity_sha256": identity_hash,
        "planning_hashes": planning_hashes,
        "character_state": character_state,
        "environment_state": environment_state,
        "prop_state": prop_state,
        "reference_pack": reference_pack,
    }
    _write_json(root / "planning" / "visual_contract.json", contract)
    _write_json(root / "review" / "reference-pack.json", reference_pack)
    return {
        "schema_version": SCHEMA_VERSION,
        "visual_contract": "planning/visual_contract.json",
        "reference_pack": "review/reference-pack.json",
        "character_count": len(character_state),
        "environment_count": len(environment_state),
        "prop_count": len(prop_state),
        "panel_count": len(panel_locks),
    }


def validate_visual_contract(project: str | Path, *, raise_on_fail: bool = True) -> dict[str, Any]:
    root = Path(project)
    episode = load_episode(root)
    environment_bible = _read_json(root / "planning" / "environment_bible.json")
    contract = _read_json(root / "planning" / "visual_contract.json")
    try:
        current_identity_hash = visual_identity_sha256(root)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        current_identity_hash = ""

    character_state = contract.get("character_state", {})
    environment_state = contract.get("environment_state", {})
    prop_state = contract.get("prop_state", {})
    reference_pack = contract.get("reference_pack", {})
    panel_locks = reference_pack.get("panel_locks", {}) if isinstance(reference_pack, dict) else {}
    planning_hashes = contract.get("planning_hashes")
    if not isinstance(planning_hashes, dict):
        planning_hashes = {}

    if not isinstance(character_state, dict):
        character_state = {}
    if not isinstance(environment_state, dict):
        environment_state = {}
    if not isinstance(prop_state, dict):
        prop_state = {}
    if not isinstance(panel_locks, dict):
        panel_locks = {}
    contract_identity_hash = str(contract.get("visual_identity_sha256") or reference_pack.get("visual_identity_sha256") or "")
    visual_identity_hash_match = bool(contract_identity_hash) and contract_identity_hash == current_identity_hash
    planning_hash_matches = _planning_hash_matches(root, planning_hashes)

    character_aliases = _contract_character_aliases(character_state)
    environment_aliases = _environment_aliases(_environment_records(environment_bible))
    panel_contexts = _panel_contexts(episode, environment_aliases)

    unknown_characters: dict[str, list[str]] = {}
    missing_character_locks: dict[str, list[str]] = {}
    unknown_environments: dict[str, str] = {}
    missing_environment_anchors: list[str] = []
    missing_prop_states: dict[str, list[str]] = {}
    missing_panel_locks: list[str] = []

    character_refs = 0
    known_character_refs = 0
    prop_refs = 0
    known_prop_refs = 0
    anchored_environment_refs = 0

    for context in panel_contexts:
        panel_id = context["panel_id"]
        panel_lock = panel_locks.get(panel_id)
        if not isinstance(panel_lock, dict):
            missing_panel_locks.append(panel_id)
            panel_lock = {}

        present = _string_list(context["panel"].get("characters_present"))
        panel_unknown_characters: list[str] = []
        panel_missing_locks: list[str] = []
        wardrobe_state = panel_lock.get("wardrobe_state", {})
        if not isinstance(wardrobe_state, dict):
            wardrobe_state = {}
        for character in present:
            character_refs += 1
            canonical = character_aliases.get(character)
            if not canonical:
                panel_unknown_characters.append(character)
                continue
            known_character_refs += 1
            if not str(wardrobe_state.get(canonical, "")).strip():
                panel_missing_locks.append(canonical)
        if panel_unknown_characters:
            unknown_characters[panel_id] = sorted(panel_unknown_characters)
        if panel_missing_locks:
            missing_character_locks[panel_id] = sorted(panel_missing_locks)

        environment_id = str(panel_lock.get("environment_id") or context["environment_id"])
        if environment_id not in environment_state:
            unknown_environments[panel_id] = environment_id
        elif _environment_has_anchor(environment_state[environment_id]):
            anchored_environment_refs += 1
        else:
            missing_environment_anchors.append(environment_id)

        props = _panel_props(context["panel"])
        panel_missing_props: list[str] = []
        for prop_id, prop_value in props.items():
            prop_refs += 1
            state = str(prop_value).strip()
            if prop_id in prop_state and state:
                known_prop_refs += 1
            else:
                panel_missing_props.append(prop_id)
        if panel_missing_props:
            missing_prop_states[panel_id] = sorted(panel_missing_props)

    panel_count = len(panel_contexts)
    character_lock_coverage = (
        known_character_refs / character_refs
        if character_refs
        else 1.0
    )
    if character_refs and missing_character_locks:
        character_lock_coverage = max(0.0, (known_character_refs - sum(len(v) for v in missing_character_locks.values())) / character_refs)
    environment_anchor_coverage = anchored_environment_refs / panel_count if panel_count else 0.0
    prop_persistence_coverage = known_prop_refs / prop_refs if prop_refs else 1.0
    reference_pack_ready = (
        bool(reference_pack)
        and len(panel_locks) == panel_count
        and not missing_panel_locks
        and not unknown_characters
        and not unknown_environments
        and visual_identity_hash_match
        and all(planning_hash_matches.values())
    )
    passed = (
        round(character_lock_coverage, 4) == 1.0
        and round(environment_anchor_coverage, 4) == 1.0
        and round(prop_persistence_coverage, 4) == 1.0
        and reference_pack_ready
        and visual_identity_hash_match
        and all(planning_hash_matches.values())
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": _now(),
        "passed": passed,
        "metrics": {
            "panel_count": panel_count,
            "character_lock_coverage": round(character_lock_coverage, 4),
            "environment_anchor_coverage": round(environment_anchor_coverage, 4),
            "prop_persistence_coverage": round(prop_persistence_coverage, 4),
            "reference_pack_ready": reference_pack_ready,
            "visual_identity_hash_match": visual_identity_hash_match,
            "planning_hash_matches": planning_hash_matches,
        },
        "visual_identity_sha256": {
            "contract": contract_identity_hash,
            "current": current_identity_hash,
        },
        "unknown_characters": unknown_characters,
        "missing_character_locks": missing_character_locks,
        "unknown_environments": unknown_environments,
        "missing_environment_anchors": sorted(set(missing_environment_anchors)),
        "missing_prop_states": missing_prop_states,
        "missing_panel_locks": missing_panel_locks,
        "planning_hashes": {
            "contract": planning_hashes,
            "current": _planning_hashes(root),
        },
    }
    _write_json(root / "qa" / "visual-contract-report.json", report)
    if raise_on_fail and not passed:
        raise ValueError("Visual contract validation failed.")
    return report


def _ensure_distinctiveness_report(root: Path) -> dict[str, Any]:
    report_path = root / "qa" / "distinctiveness-report.json"
    if report_path.exists():
        data = _read_json(report_path)
        if data.get("passed"):
            return data
    return validate_distinctiveness(root)


def _distinctiveness_status(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "passed": bool(report.get("passed")),
        "status": str(report.get("status", "")),
        "highest_similarity": report.get("highest_similarity", 0.0),
        "compared_projects": report.get("compared_projects", []),
    }


def _build_character_state(
    panel_contexts: list[dict[str, Any]],
    character_records: dict[str, dict[str, Any]],
    character_aliases: dict[str, str],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for char_id, record in character_records.items():
        panel_ids: list[str] = []
        wardrobe_by_panel: dict[str, str] = {}
        for context in panel_contexts:
            panel = context["panel"]
            present = _string_list(panel.get("characters_present"))
            if not any(character_aliases.get(item) == char_id for item in present):
                continue
            panel_id = context["panel_id"]
            panel_ids.append(panel_id)
            wardrobe_by_panel[panel_id] = _panel_wardrobe(panel, char_id, record)
        result[char_id] = {
            "id": char_id,
            "name": str(record.get("name", "")),
            "role": str(record.get("role", "")),
            "identity_anchor": str(record.get("visual") or record.get("prompt_fragment") or record.get("name") or char_id),
            "visual": str(record.get("visual", "")),
            "personality": str(record.get("personality", "")),
            "prompt_fragment": str(record.get("prompt_fragment", "")),
            "wardrobe_lock": _lock_value(record.get("wardrobe_lock")),
            "prop_lock": _lock_value(record.get("prop_lock")),
            "panel_ids": panel_ids,
            "first_panel": panel_ids[0] if panel_ids else "",
            "last_panel": panel_ids[-1] if panel_ids else "",
            "wardrobe_by_panel": wardrobe_by_panel,
        }
    return result


def _build_environment_state(
    panel_contexts: list[dict[str, Any]],
    environment_records: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for env_id, record in environment_records.items():
        panel_ids = [context["panel_id"] for context in panel_contexts if context["environment_id"] == env_id]
        result[env_id] = {
            "id": env_id,
            "name": str(record.get("name", "")),
            "kind": str(record.get("kind", "")),
            "anchors": _string_list(record.get("anchors")),
            "panel_ids": panel_ids,
            "first_panel": panel_ids[0] if panel_ids else "",
            "last_panel": panel_ids[-1] if panel_ids else "",
        }
    return result


def _build_prop_state(panel_contexts: list[dict[str, Any]], prop_ids: set[str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for prop_id in sorted(prop_ids):
        panel_ids: list[str] = []
        states: list[str] = []
        states_by_panel: dict[str, str] = {}
        for context in panel_contexts:
            props = _panel_props(context["panel"])
            if prop_id not in props:
                continue
            panel_id = context["panel_id"]
            state = props[prop_id]
            panel_ids.append(panel_id)
            states_by_panel[panel_id] = state
            if state and state not in states:
                states.append(state)
        result[prop_id] = {
            "id": prop_id,
            "description": prop_id,
            "panel_ids": panel_ids,
            "first_panel": panel_ids[0] if panel_ids else "",
            "last_panel": panel_ids[-1] if panel_ids else "",
            "states": states,
            "states_by_panel": states_by_panel,
        }
    return result


def _build_panel_locks(
    panel_contexts: list[dict[str, Any]],
    character_records: dict[str, dict[str, Any]],
    character_aliases: dict[str, str],
    environment_aliases: dict[str, str],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for context in panel_contexts:
        panel = context["panel"]
        panel_id = context["panel_id"]
        characters_present = _string_list(panel.get("characters_present"))
        wardrobe_state: dict[str, str] = {}
        for character in characters_present:
            canonical = character_aliases.get(character)
            if canonical and canonical in character_records:
                wardrobe_state[canonical] = _panel_wardrobe(panel, canonical, character_records[canonical])
        result[panel_id] = {
            "panel_id": panel_id,
            "scene_id": context["scene_id"],
            "reading_order": context["reading_order"],
            "characters_present": characters_present,
            "environment_id": environment_aliases.get(context["raw_environment_id"], context["environment_id"]),
            "wardrobe_state": wardrobe_state,
            "props_and_states": _panel_props(panel),
            "continuity_from_prev": str(panel.get("continuity_from_prev") or panel.get("continuity_from") or ""),
            "lettering_safe_zone": ", ".join(_string_list(panel.get("caption_safe_zones"))) or str(panel.get("lettering_safe_zone", "")),
            "source_refs": _string_list(panel.get("source_refs")),
        }
    return result


def _panel_contexts(episode: dict[str, Any], environment_aliases: dict[str, str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    scenes = episode.get("scenes")
    if isinstance(scenes, list) and scenes:
        for scene_index, scene in enumerate(scenes, start=1):
            if not isinstance(scene, dict):
                continue
            scene_id = str(scene.get("scene_id") or f"S{scene_index:02d}")
            scene_environment = str(scene.get("location") or scene.get("setting") or "")
            panels = scene.get("panels", [])
            if not isinstance(panels, list):
                continue
            for panel_index, panel in enumerate(panels, start=1):
                if not isinstance(panel, dict):
                    continue
                result.append(_panel_context(panel, len(result) + 1, scene_id, scene_environment, environment_aliases))
        return result
    return result


def _panel_context(
    panel: dict[str, Any],
    fallback_index: int,
    scene_id: str,
    scene_environment: str,
    environment_aliases: dict[str, str],
) -> dict[str, Any]:
    panel_id = str(panel.get("panel_id") or f"P{fallback_index:02d}")
    raw_environment = str(panel.get("environment_id") or panel.get("setting") or panel.get("location") or scene_environment)
    environment_id = environment_aliases.get(raw_environment, raw_environment)
    reading_order = panel.get("reading_order")
    if not isinstance(reading_order, int):
        reading_order = fallback_index
    return {
        "panel": panel,
        "panel_id": panel_id,
        "scene_id": scene_id,
        "raw_environment_id": raw_environment,
        "environment_id": environment_id,
        "reading_order": reading_order,
    }


def _character_records(character_bible: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    characters = character_bible.get("characters", [])
    if not isinstance(characters, list):
        return result
    for index, character in enumerate(characters, start=1):
        if not isinstance(character, dict):
            continue
        char_id = str(character.get("id") or character.get("name") or f"character-{index}")
        if char_id:
            result[char_id] = character
    return result


def _environment_records(environment_bible: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    environments = environment_bible.get("environments", [])
    if not isinstance(environments, list):
        return result
    for index, environment in enumerate(environments, start=1):
        if not isinstance(environment, dict):
            continue
        env_id = str(environment.get("id") or environment.get("name") or f"environment-{index}")
        if env_id:
            result[env_id] = environment
    return result


def _character_aliases(character_records: dict[str, dict[str, Any]]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for char_id, record in character_records.items():
        aliases[char_id] = char_id
        name = str(record.get("name", "")).strip()
        if name:
            aliases[name] = char_id
    return aliases


def _contract_character_aliases(character_state: dict[str, Any]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for char_id, state in character_state.items():
        aliases[str(char_id)] = str(char_id)
        if isinstance(state, dict):
            name = str(state.get("name", "")).strip()
            if name:
                aliases[name] = str(char_id)
    return aliases


def _environment_aliases(environment_records: dict[str, dict[str, Any]]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for env_id, record in environment_records.items():
        aliases[env_id] = env_id
        name = str(record.get("name", "")).strip()
        if name:
            aliases[name] = env_id
    return aliases


def _episode_prop_ids(
    panel_contexts: list[dict[str, Any]],
    character_records: dict[str, dict[str, Any]],
) -> set[str]:
    prop_ids: set[str] = set()
    for record in character_records.values():
        prop_ids.update(_prop_lock_ids(record.get("prop_lock")))
    for context in panel_contexts:
        prop_ids.update(_panel_props(context["panel"]).keys())
    return {item for item in prop_ids if item}


def _prop_lock_ids(value: object) -> set[str]:
    if isinstance(value, list):
        return {str(item).strip() for item in value if str(item).strip()}
    text = str(value or "").strip()
    if not text:
        return set()
    return {item.strip() for item in re.split(r"[,，、;；]+", text) if item.strip()}


def _panel_props(panel: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    props_and_states = panel.get("props_and_states")
    if isinstance(props_and_states, dict):
        for prop_id, state in props_and_states.items():
            prop_key = str(prop_id).strip()
            if prop_key:
                result[prop_key] = str(state).strip()
    for prop in _string_list(panel.get("props")):
        result.setdefault(prop, prop)
    return result


def _panel_wardrobe(panel: dict[str, Any], char_id: str, record: dict[str, Any]) -> str:
    wardrobe_state = panel.get("wardrobe_state")
    if isinstance(wardrobe_state, dict):
        for key in (char_id, str(record.get("name", ""))):
            value = str(wardrobe_state.get(key, "")).strip()
            if value:
                return value
    return _lock_value(record.get("wardrobe_lock"))


def _environment_has_anchor(state: object) -> bool:
    if not isinstance(state, dict):
        return False
    return bool(_string_list(state.get("anchors")) or str(state.get("name", "")).strip())


def _lock_value(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "").strip()


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []


def _planning_hashes(root: Path) -> dict[str, str]:
    hashes = {
        "character_bible_sha256": _file_sha256(root / "planning" / "character_bible.json"),
        "environment_bible_sha256": _file_sha256(root / "planning" / "environment_bible.json"),
        "world_model_sha256": world_model_sha256(root),
        "page_plan_sha256": page_plan_sha256(root),
    }
    return {key: value for key, value in hashes.items() if value}


def _planning_hash_matches(root: Path, contract_hashes: dict[str, Any]) -> dict[str, bool]:
    current = _planning_hashes(root)
    result: dict[str, bool] = {}
    for key, value in contract_hashes.items():
        expected = str(value or "").strip()
        if not expected:
            continue
        result[key] = current.get(key, "") == expected
    return result


def _file_sha256(path: Path) -> str:
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _world_model_summary(root: Path) -> dict[str, Any]:
    data = _read_optional_json(root / "planning" / "world_model.json")
    if not data:
        return {}
    return {
        "era": str(data.get("era") or ""),
        "geography": str(data.get("geography") or ""),
        "institutions": _string_list(data.get("institutions")),
        "material_culture": _string_list(data.get("material_culture")),
        "access_rules": _string_list(data.get("access_rules")),
    }


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Required file is missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
