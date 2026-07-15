from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .prompt_compiler import reference_pack_panel_lock_lines, visual_identity_lock_lines
from .project_layout import load_episode, resolve_episode_id, validate_episode_id


DEFAULT_EPISODE_ID = "EP01"
# Portrait 3:4 to match DEFAULT_PANEL_ASPECT_RATIO (audit E2). The old 1536x1024
# landscape default contradicted the 3:4 delivery target and the aspect gate.
DEFAULT_WIDTH = 1152
DEFAULT_HEIGHT = 1536
DEFAULT_QUALITY = "high"
ADAPTER_ID = "codex-exec-image-worker"


def prepare_host_image_batch(
    project_dir: str | Path,
    episode_id: str | None = None,
    batch_dir: str | Path | None = None,
    image_dir: str | Path | None = None,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    quality: str = DEFAULT_QUALITY,
) -> dict[str, object]:
    """Write host-image worker jobs for a project episode.

    This does not generate images. It compiles deterministic prompts and output
    filenames so a save-capable host image worker can write panel PNGs that are
    later accepted through import_host_image_panels.
    """
    if width <= 0 or height <= 0:
        raise ValueError("Image width and height must be positive")
    root = Path(project_dir)
    episode = load_episode(root)
    # The id becomes a directory name below — shape-validate it even when it
    # comes from the episode file itself (release audit P1-1).
    episode_id = validate_episode_id(resolve_episode_id(episode, episode_id))
    panels = _episode_panels(episode)
    if not isinstance(panels, list) or not panels:
        raise ValueError(f"Official episode has no panels: {root / 'story' / 'episode-001.json'}")

    final_batch_dir = Path(batch_dir) if batch_dir else root / "host-image-batch" / episode_id
    final_image_dir = Path(image_dir) if image_dir else root / "host-image-output" / episode_id
    final_batch_dir.mkdir(parents=True, exist_ok=True)
    final_image_dir.mkdir(parents=True, exist_ok=True)

    project = _load_optional_json(root / "project.json")
    style_bible = _load_optional_json(root / "planning" / "style_bible.json")
    character_bible = _load_optional_json(root / "planning" / "character_bible.json")
    environment_bible = _load_optional_json(root / "planning" / "environment_bible.json")
    reference_pack = _load_reference_pack(root)
    visual_identity = _load_optional_json(root / "planning" / "visual_identity.json")

    jobs = [
        _job_for_panel(
            root=root,
            episode=episode,
            project=project,
            style_bible=style_bible,
            character_bible=character_bible,
            environment_bible=environment_bible,
            reference_pack=reference_pack,
            visual_identity=visual_identity,
            panel=panel,
            index=index,
            width=width,
            height=height,
            quality=quality,
        )
        for index, panel in enumerate(panels, start=1)
        if isinstance(panel, dict)
    ]
    if len(jobs) != len(panels):
        raise ValueError("Episode panels must be JSON objects")

    jobs_path = final_batch_dir / "jobs.jsonl"
    jobs_path.write_text(
        "\n".join(json.dumps(job, ensure_ascii=False) for job in jobs) + "\n",
        encoding="utf-8",
    )

    manifest = {
        "schema_version": "1.0",
        "backend": "host-image",
        "adapter": ADAPTER_ID,
        "episode_id": episode_id,
        "panel_count": len(jobs),
        "image_size": f"{width}x{height}",
        "quality": quality,
        "jobs_file": _display_path(root, jobs_path),
        "image_dir": _display_path(root, final_image_dir),
        "import_command": (
            "python -m book_to_comic import-host-images "
            f"{_quote_path(root)} --episode {episode_id} --image-dir {_quote_path(final_image_dir)}"
        ),
        "round_trip_required": True,
        "notes": [
            "Run these jobs only in an environment with native image generation that can save PNG files.",
            "If the current Codex/Claude host exposes a built-in image generation tool, the active agent should call it for each job and copy the saved result into image_dir without asking the user to move files.",
            "Do not accept chat preview images until they are saved or recovered as files.",
            "After generation, import and validate the PNGs with import-host-images before compose/export.",
        ],
    }
    manifest_path = final_batch_dir / "manifest.json"
    _write_json(manifest_path, manifest)

    instructions_path = final_batch_dir / "worker-instructions.md"
    instructions_path.write_text(
        _worker_instructions(
            root=root,
            jobs_path=jobs_path,
            image_dir=final_image_dir,
            episode_id=episode_id,
            panel_count=len(jobs),
        ),
        encoding="utf-8",
    )

    return {
        "project_dir": str(root),
        "episode_id": episode_id,
        "backend": "host-image",
        "adapter": ADAPTER_ID,
        "panel_count": len(jobs),
        "batch_dir": str(final_batch_dir),
        "image_dir": str(final_image_dir),
        "jobs_file": str(jobs_path),
        "manifest": str(manifest_path),
        "instructions": str(instructions_path),
    }


def _job_for_panel(
    *,
    root: Path,
    episode: dict[str, Any],
    project: dict[str, Any],
    style_bible: dict[str, Any],
    character_bible: dict[str, Any],
    environment_bible: dict[str, Any],
    reference_pack: dict[str, Any],
    visual_identity: dict[str, Any],
    panel: dict[str, Any],
    index: int,
    width: int,
    height: int,
    quality: str,
) -> dict[str, object]:
    panel_id = str(panel.get("panel_id") or f"P{index:02d}")
    prompt = _compile_panel_prompt(
        episode=episode,
        project=project,
        style_bible=style_bible,
        character_bible=character_bible,
        environment_bible=environment_bible,
        reference_pack=reference_pack,
        visual_identity=visual_identity,
        panel=panel,
        width=width,
        height=height,
        quality=quality,
    )
    return {
        "id": f"{episode.get('episode_id', DEFAULT_EPISODE_ID)}-{panel_id}",
        "episode_id": episode.get("episode_id", DEFAULT_EPISODE_ID),
        "panel_id": panel_id,
        "output": f"{index:02d}.png",
        "prompt": prompt,
        "size": f"{width}x{height}",
        "quality": quality,
        "context": {
            "book_title": episode.get("book_title", project.get("project_title", "")),
            "episode_title": episode.get("episode_title", ""),
            "style_id": episode.get("style_id", style_bible.get("style_id", "")),
            "source_refs": panel.get("source_refs", []),
            "root": _display_path(root, root),
        },
    }


def _compile_panel_prompt(
    *,
    episode: dict[str, Any],
    project: dict[str, Any],
    style_bible: dict[str, Any],
    character_bible: dict[str, Any],
    environment_bible: dict[str, Any],
    reference_pack: dict[str, Any],
    visual_identity: dict[str, Any],
    panel: dict[str, Any],
    width: int,
    height: int,
    quality: str,
) -> str:
    book_title = episode.get("book_title") or project.get("project_title") or "book-to-comic"
    style = style_bible.get("visual_language") or "premium editorial comic illustration"
    image_prompt = str(panel.get("image_prompt") or panel.get("visual") or panel.get("action") or "").strip()
    negative = str(panel.get("negative_prompt") or "").strip()
    panel_id = str(panel.get("panel_id", ""))
    characters = _characters_for_panel(panel, character_bible, reference_pack)
    environment = _environment_for_panel(panel, environment_bible, reference_pack)
    continuity = str(panel.get("continuity") or panel.get("continuity_from") or "").strip()
    text_context = _text_context(panel)
    visual_contract_lines = reference_pack_panel_lock_lines(panel_id, reference_pack)
    visual_identity_lines = visual_identity_lock_lines(reference_pack=reference_pack, visual_identity=visual_identity)

    return "\n".join(
        line
        for line in [
            "Use case: illustration-story",
            "Asset type: high-quality comic panel for book-to-comic",
            f"Canvas: {width}x{height}, quality {quality}",
            f"Book: {book_title}",
            f"Episode: {episode.get('episode_title', '')}",
            f"Panel: {panel.get('panel_id', '')} / {panel.get('beat', '')}",
            f"Style/medium: {style}",
            *visual_identity_lines,
            *visual_contract_lines,
            f"Scene/backdrop: {environment}",
            f"Characters to include: {characters}",
            f"Action and composition: {image_prompt}",
            f"Continuity: {continuity}" if continuity else "",
            f"Story context, not rendered as text: {text_context}" if text_context else "",
            "Text handling: no readable text, no letters, no numbers, no pseudo-text, no captions, no speech bubbles. All dialogue, captions, and post-production lettering are added later by the comic layout renderer.",
            "Composition: leave natural negative space where captions can be added later, but do not draw caption boxes.",
            "Full-bleed: the artwork must fill the entire canvas edge to edge — no borders, no frame lines, no mats, no letterboxing or flat margins.",
            f"Avoid: {negative}; watermark, logo, UI, chart, blank panel, placeholder art, distorted hands, inconsistent wardrobe.",
        ]
        if line
    )


def _characters_for_panel(panel: dict[str, Any], character_bible: dict[str, Any], reference_pack: dict[str, Any]) -> str:
    present = _locked_characters(panel, reference_pack) or [str(item) for item in panel.get("characters_present", [])]
    present_set = set(present)
    reference_characters = reference_pack.get("characters")
    if isinstance(reference_characters, dict):
        lines: list[str] = []
        panel_lock = _panel_lock(panel, reference_pack)
        wardrobe_state = panel_lock.get("wardrobe_state") if isinstance(panel_lock, dict) else {}
        for key in present:
            entry = reference_characters.get(key)
            if not isinstance(entry, dict):
                continue
            parts = [str(entry.get("prompt_fragment") or entry.get("visual") or entry.get("name") or key)]
            lock = str(entry.get("wardrobe_lock") or "").strip()
            if lock:
                parts.append(f"wardrobe_lock: {lock}")
            if isinstance(wardrobe_state, dict) and wardrobe_state.get(key):
                parts.append(f"panel wardrobe: {wardrobe_state[key]}")
            lines.append(f"{key}: " + "; ".join(part for part in parts if part))
        if lines:
            return " | ".join(lines)
    characters = character_bible.get("characters", [])
    if not isinstance(characters, list) or not characters:
        return ", ".join(sorted(present_set)) or "only characters explicitly listed for this panel"

    lines: list[str] = []
    for character in characters:
        if not isinstance(character, dict):
            continue
        name = str(character.get("name") or character.get("id") or "")
        cid = str(character.get("id") or "")
        if present_set and name not in present_set and cid not in present_set:
            continue
        fragment = character.get("prompt_fragment") or character.get("visual") or character.get("role") or ""
        locks = [character.get("wardrobe_lock"), character.get("prop_lock")]
        lock_text = ", ".join(str(item) for item in locks if item)
        lines.append(f"{name}: {fragment}" + (f"; locks: {lock_text}" if lock_text else ""))
    return " | ".join(lines) if lines else ", ".join(sorted(present_set))


def _environment_for_panel(panel: dict[str, Any], environment_bible: dict[str, Any], reference_pack: dict[str, Any]) -> str:
    panel_lock = _panel_lock(panel, reference_pack)
    setting = str(panel_lock.get("environment_id") or panel.get("setting") or "")
    reference_environments = reference_pack.get("environments")
    if isinstance(reference_environments, dict):
        environment = reference_environments.get(setting)
        if isinstance(environment, dict):
            anchors = environment.get("anchors", [])
            anchor_text = ", ".join(str(item) for item in anchors) if isinstance(anchors, list) else str(anchors)
            return f"{environment.get('name', setting)}; kind: {environment.get('kind', '')}; anchors: {anchor_text}"
    environments = environment_bible.get("environments", [])
    if isinstance(environments, list):
        for environment in environments:
            if not isinstance(environment, dict):
                continue
            if setting and setting not in {str(environment.get("id")), str(environment.get("name"))}:
                continue
            anchors = environment.get("anchors", [])
            anchor_text = ", ".join(str(item) for item in anchors) if isinstance(anchors, list) else str(anchors)
            return f"{environment.get('name', setting)}; anchors: {anchor_text}"
    return setting or str(panel.get("visual") or "")


def _locked_characters(panel: dict[str, Any], reference_pack: dict[str, Any]) -> list[str]:
    panel_lock = _panel_lock(panel, reference_pack)
    value = panel_lock.get("characters_present") if isinstance(panel_lock, dict) else None
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _panel_lock(panel: dict[str, Any], reference_pack: dict[str, Any]) -> dict[str, Any]:
    panel_locks = reference_pack.get("panel_locks")
    if not isinstance(panel_locks, dict):
        return {}
    panel_id = str(panel.get("panel_id") or "")
    lock = panel_locks.get(panel_id)
    return lock if isinstance(lock, dict) else {}


def _text_context(panel: dict[str, Any]) -> str:
    chunks: list[str] = []
    for key in ("dialogue", "narration", "reality_mapping", "comment_hook"):
        value = panel.get(key)
        if isinstance(value, list):
            chunks.extend(str(item) for item in value if item)
        elif value:
            chunks.append(str(value))
    return " / ".join(chunks)


def _episode_panels(episode: dict[str, Any]) -> list[Any]:
    panels = episode.get("panels")
    if isinstance(panels, list) and panels:
        return panels
    scenes = episode.get("scenes")
    if not isinstance(scenes, list):
        return []
    result: list[Any] = []
    for scene in scenes:
        if isinstance(scene, dict) and isinstance(scene.get("panels"), list):
            result.extend(scene["panels"])
    return result


def _worker_instructions(
    *,
    root: Path,
    jobs_path: Path,
    image_dir: Path,
    episode_id: str,
    panel_count: int,
) -> str:
    return (
        "# Host Image Batch\n\n"
        f"- Jobs: `{_display_path(root, jobs_path)}`\n"
        f"- Output directory: `{_display_path(root, image_dir)}`\n"
        f"- Expected images: `{panel_count}` PNG files named `01.png` through `{panel_count:02d}.png`\n\n"
        "Run the jobs only with a host image backend that can save PNG files. "
        "A chat preview is not enough; each generated image must exist in the output directory. "
        "When the active Codex/Claude session has a built-in image generation tool, the agent should call it once per job, then copy or move the saved output from the host generated-images folder into the exact filename below without asking the user to handle files.\n\n"
        "After image generation succeeds, import the accepted files:\n\n"
        "```bash\n"
        f"python -m book_to_comic import-host-images {_quote_path(root)} --episode {episode_id} --image-dir {_quote_path(image_dir)}\n"
        "```\n\n"
        "Then run:\n\n"
        "```bash\n"
        f"python -m book_to_comic compose {_quote_path(root)}\n"
        f"python -m book_to_comic export {_quote_path(root)} --formats pdf,cbz,epub,long-image,zip\n"
        "```\n"
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return _read_json(path)
    except (OSError, json.JSONDecodeError):
        return {}


def _load_reference_pack(root: Path) -> dict[str, Any]:
    reference_path = root / "review" / "reference-pack.json"
    if reference_path.exists():
        return _load_optional_json(reference_path)
    contract_path = root / "planning" / "visual_contract.json"
    contract = _load_optional_json(contract_path)
    reference_pack = contract.get("reference_pack")
    return reference_pack if isinstance(reference_pack, dict) else {}


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _display_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _quote_path(path: Path) -> str:
    text = str(path)
    return f'"{text}"' if " " in text else text
