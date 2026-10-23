from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .delivery_config import DEFAULT_PANEL_ASPECT_RATIO, project_panel_aspect_ratio
from .models import PanelArtSpec
from .narrative_identity import DEFAULT_LANGUAGE
from .project_layout import load_episode, resolve_episode_id
from .prompt_compiler import compile_panel_prompt
from .styles import get_style
from .text_prompt_compiler import compile_panel_text_prompt


DEFAULT_EPISODE_ID = "EP01"


def export_project_prompts(
    project_dir: str | Path,
    episode_id: str | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, object]:
    root = Path(project_dir)
    episode = load_episode(root)
    episode_id = resolve_episode_id(episode, episode_id)
    panels = _episode_panels(episode)
    if not isinstance(panels, list) or not panels:
        raise ValueError(f"Episode has no panels: {root / 'story' / 'episode-001.json'}")

    final_output_dir = Path(output_dir) if output_dir else root / "prompts"
    final_output_dir.mkdir(parents=True, exist_ok=True)

    style = get_style(str(episode.get("style_id") or "editorial"))
    characters = _project_characters(root)
    environments = _project_environments(root)
    reference_pack = _load_reference_pack(root)
    visual_identity = _load_optional_json(root / "planning" / "visual_identity.json")
    default_aspect = project_panel_aspect_ratio(root)

    prompts: list[dict[str, str]] = []
    for index, panel in enumerate(panels, start=1):
        if not isinstance(panel, Mapping):
            raise ValueError("Episode panels must be JSON objects")
        panel_data = dict(panel)
        panel_id = str(panel_data.get("panel_id") or f"P{index:02d}")
        prompt_path = final_output_dir / f"panel-{index:02d}.txt"
        prompt_path.write_text(
            compile_panel_prompt(
                style,
                _panel_art_spec(panel_data, panel_id, default_aspect_ratio=default_aspect),
                characters=characters,
                environments=environments,
                props=_project_props(panel_data),
                reference_pack=reference_pack,
                visual_identity=visual_identity,
            ),
            encoding="utf-8",
        )
        prompts.append(
            {
                "panel_id": panel_id,
                "path": _display_path(root, prompt_path),
            }
        )

    manifest = {
        "schema_version": "1.0",
        "episode_id": episode_id,
        "panel_count": len(prompts),
        "prompts": prompts,
    }
    manifest_path = final_output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "project_dir": str(root),
        "episode_id": episode_id,
        "panel_count": len(prompts),
        "prompt_dir": str(final_output_dir),
        "manifest": str(manifest_path),
        "prompts": prompts,
    }


def export_project_text_prompts(
    project_dir: str | Path,
    episode_id: str | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, object]:
    root = Path(project_dir)
    episode = load_episode(root)
    episode_id = resolve_episode_id(episode, episode_id)
    panels = _episode_panels(episode)
    if not isinstance(panels, list) or not panels:
        raise ValueError(f"Episode has no panels: {root / 'story' / 'episode-001.json'}")

    final_output_dir = Path(output_dir) if output_dir else root / "text-prompts"
    final_output_dir.mkdir(parents=True, exist_ok=True)
    narrative_identity = _load_optional_json(root / "planning" / "narrative_identity.json")
    language = str(narrative_identity.get("language") or DEFAULT_LANGUAGE).strip() or DEFAULT_LANGUAGE
    scene_by_panel = _scene_by_panel(episode)

    prompts: list[dict[str, str]] = []
    for index, panel in enumerate(panels, start=1):
        if not isinstance(panel, Mapping):
            raise ValueError("Episode panels must be JSON objects")
        panel_data = dict(panel)
        panel_id = str(panel_data.get("panel_id") or f"P{index:02d}")
        prompt_path = final_output_dir / f"panel-{index:02d}.{language}.md"
        prompt_path.write_text(
            compile_panel_text_prompt(
                panel_data,
                narrative_identity=narrative_identity,
                episode=episode,
                scene=scene_by_panel.get(panel_id, {}),
                previous_panel=dict(panels[index - 2]) if index > 1 and isinstance(panels[index - 2], Mapping) else None,
                next_panel=dict(panels[index]) if index < len(panels) and isinstance(panels[index], Mapping) else None,
            ),
            encoding="utf-8",
        )
        prompts.append({"panel_id": panel_id, "path": _display_path(root, prompt_path)})

    manifest = {
        "schema_version": "1.0",
        "episode_id": episode_id,
        "panel_count": len(prompts),
        "prompt_type": f"{language}-lettering",
        "prompts": prompts,
    }
    manifest_path = final_output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "project_dir": str(root),
        "episode_id": episode_id,
        "panel_count": len(prompts),
        "prompt_dir": str(final_output_dir),
        "manifest": str(manifest_path),
        "prompts": prompts,
    }


def _panel_art_spec(panel: dict[str, Any], panel_id: str, default_aspect_ratio: str = DEFAULT_PANEL_ASPECT_RATIO) -> PanelArtSpec:
    return PanelArtSpec(
        panel_id=panel_id,
        characters_present=tuple(str(item) for item in panel.get("characters_present", ())),
        environment_id=str(panel.get("setting") or panel.get("environment_id") or ""),
        time=str(panel.get("time", "")),
        shot_size=str(panel.get("shot_size", "medium")),
        camera_angle=str(panel.get("camera_angle", "eye-level")),
        lens_feel=str(panel.get("lens_feel", "natural")),
        focal_point=str(panel.get("focal_point") or panel.get("visual") or ""),
        foreground=str(panel.get("foreground", "")),
        midground=str(panel.get("midground", "")),
        background=str(panel.get("background", "")),
        action=str(panel.get("action") or panel.get("visual") or ""),
        emotion=str(panel.get("emotion", "")),
        eyeline=str(panel.get("eyeline", "")),
        props_and_states=_panel_props_and_states(panel),
        continuity_from=str(panel.get("continuity_from", "")),
        transition_to_next=str(panel.get("transition_to_next", "")),
        lettering_safe_zone=", ".join(str(item) for item in panel.get("caption_safe_zones", ()))
        or "natural negative space",
        aspect_ratio=str(panel.get("aspect_ratio") or default_aspect_ratio),
    )


def _episode_panels(episode: dict[str, Any]) -> list[Any]:
    panels = episode.get("panels")
    if isinstance(panels, list) and panels:
        return panels
    scenes = episode.get("scenes")
    if not isinstance(scenes, list):
        return []
    result: list[Any] = []
    for scene in scenes:
        if isinstance(scene, Mapping) and isinstance(scene.get("panels"), list):
            result.extend(scene["panels"])
    return result


def _scene_by_panel(episode: dict[str, Any]) -> dict[str, dict[str, Any]]:
    scenes = episode.get("scenes")
    if not isinstance(scenes, list):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for scene in scenes:
        if not isinstance(scene, Mapping) or not isinstance(scene.get("panels"), list):
            continue
        scene_data = {key: value for key, value in scene.items() if key != "panels"}
        for index, panel in enumerate(scene["panels"], start=1):
            if not isinstance(panel, Mapping):
                continue
            panel_id = str(panel.get("panel_id") or f"P{index:02d}")
            result[panel_id] = dict(scene_data)
    return result


def _project_characters(root: Path) -> dict[str, str]:
    data = _load_optional_json(root / "planning" / "character_bible.json")
    characters: dict[str, str] = {}
    for item in data.get("characters", []):
        if not isinstance(item, Mapping):
            continue
        value = item.get("prompt_fragment") or item.get("visual") or item.get("name")
        if not value:
            continue
        if item.get("id"):
            characters[str(item["id"])] = str(value)
        if item.get("name"):
            characters[str(item["name"])] = str(value)
    return characters


def _project_environments(root: Path) -> dict[str, str]:
    data = _load_optional_json(root / "planning" / "environment_bible.json")
    environments: dict[str, str] = {}
    for item in data.get("environments", []):
        if not isinstance(item, Mapping):
            continue
        anchors = item.get("anchors", [])
        anchor_text = ", ".join(str(anchor) for anchor in anchors) if isinstance(anchors, list) else str(anchors)
        environments[str(item.get("id") or item.get("name") or "")] = f"{item.get('name', '')}; anchors: {anchor_text}".strip()
    return environments


def _project_props(panel: dict[str, Any]) -> dict[str, str]:
    props: dict[str, str] = {}
    for item in panel.get("props", ()):
        props[str(item)] = str(item)
    return props


def _panel_props_and_states(panel: dict[str, Any]) -> dict[str, str]:
    value = panel.get("props_and_states")
    if isinstance(value, Mapping):
        return {str(key): str(item) for key, item in value.items()}
    return {str(item): str(item) for item in panel.get("props", ())}


def _load_reference_pack(root: Path) -> dict[str, Any]:
    reference_path = root / "review" / "reference-pack.json"
    if reference_path.exists():
        return _load_optional_json(reference_path)
    contract = _load_optional_json(root / "planning" / "visual_contract.json")
    reference_pack = contract.get("reference_pack")
    return reference_pack if isinstance(reference_pack, dict) else {}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return _read_json(path)
    except (OSError, json.JSONDecodeError):
        return {}


def _display_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)
