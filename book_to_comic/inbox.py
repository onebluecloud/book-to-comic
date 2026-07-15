"""Host-agnostic image inbox.

Any host (Codex, Claude, or no agent at all) can drop finished panel images
into the project's ``tmp/inbox/`` directory; this module exports a
human-readable "place images here" checklist and imports whatever is dropped
in. It lets a user generate art with ANY tool (Jimeng / Keling / Doubao /
Midjourney ...) without an API key and without host-specific image plumbing.

This is the official fallback for hosts that cannot generate bitmap art
themselves, so it walks the SAME quality loop as the native path (2026-07
audit P1-4):

* ``inbox-prepare`` refuses to run before the visual contract gate and the
  compiled prompt export — the user must generate from compiled prompts, not
  raw episode ``image_prompt`` drafts;
* ``inbox-import`` enforces strict ``panel-NN`` filenames, checks aspect
  ratio and resolution up front, and lands every image as a CANDIDATE via the
  same materializer the native path uses — the host then eyeballs each one
  and runs ``approve-asset``, exactly like native generation;
* every imported asset carries ``source_mode=manual-inbox`` so the delivery
  stamp can disclose that the artwork was manually imported.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from PIL import Image

from .art_style import get_custom_art_style
from .delivery_config import normalize_ratio_token, project_panel_aspect_ratio
from .project_layout import load_episode, resolve_episode_id
from .story_gate import flatten_episode_panels

INBOX_DIRNAME = "inbox"
REFINE_DIRNAME = "refine"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
README_NAME = "0_把图片放这里_README.md"
REFINE_README_NAME = "0_精修取图清单_README.md"
CHARACTER_REFERENCE_STEM = "character-reference"
# Same tolerance the compose-time aspect gate uses; failing here saves the
# user a full regeneration round instead of failing at the last gate.
ASPECT_TOLERANCE = 0.06
MIN_SHORT_SIDE = 768
RECOMMENDED_SHORT_SIDE = 1024
DEFAULT_MIN_FILE_BYTES = 100_000


def inbox_dir(root: Path) -> Path:
    return root / "tmp" / INBOX_DIRNAME


def _book_title(root: Path) -> str:
    try:
        project = json.loads((root / "project.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        return "本书"
    return str(
        project.get("book_title")
        or project.get("project_title")
        or project.get("book")
        or project.get("title")
        or "本书"
    )


def _compiled_prompt(root: Path, index: int) -> str:
    """Compiled prompts are mandatory — no fallback to raw image_prompt.

    SKILL.md's hard rule: every per-panel prompt comes from
    export-project-prompts. The old fallback quietly handed users the
    uncompiled episode draft prompt (audit P1-4a).
    """
    compiled = root / "prompts" / f"panel-{index:02d}.txt"
    if not compiled.is_file():
        raise FileNotFoundError(
            f"Compiled prompt missing: {compiled}. Run export-project-prompts first — "
            "the inbox never falls back to raw episode image_prompt drafts."
        )
    text = compiled.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Compiled prompt is empty: {compiled}. Re-run export-project-prompts.")
    return text


def _panels(root: Path) -> list:
    panels = flatten_episode_panels(load_episode(root))
    if not isinstance(panels, list) or not panels:
        raise ValueError(
            f"This episode has no panels yet: {root / 'story' / 'episode-001.json'}. "
            "Finish planning before preparing the image inbox."
        )
    return panels


def _aspect_requirement(root: Path) -> tuple[str, float | None, str]:
    """(declared token, target ratio, human-readable pixel example)."""
    declared = project_panel_aspect_ratio(root)
    token = normalize_ratio_token(declared)
    if not token:
        return declared, None, ""
    width_part, height_part = token
    ratio = width_part / height_part
    example_short = RECOMMENDED_SHORT_SIDE
    if ratio <= 1:
        example = f"{example_short}×{round(example_short / ratio)}"
    else:
        example = f"{round(example_short * ratio)}×{example_short}"
    return declared, ratio, example


PRE_IMAGE_GATE_SKIP = {
    # Needs approved panel images — cannot run before generation.
    "validate-appeal",
}


def _run_pre_image_gates(root: Path) -> None:
    """Run the SHARED formal gate registry before the user spends a
    generation round in a third-party tool.

    v5.13.0 checked only the visual contract + compiled prompts, so a user
    could generate a full image set and only then discover the planning gates
    fail (release audit P1-8). The story gate runs its deterministic core
    here (the independent llm review is recorded later, before compose).
    """
    from .artifact_materializer import _is_schema3_project, formal_compose_gates
    from .story_gate import validate_story_gate

    schema3 = _is_schema3_project(root)
    for stage, name, thunk in formal_compose_gates(root, schema3=schema3):
        if stage == "assets" or name in PRE_IMAGE_GATE_SKIP:
            continue
        try:
            if name == "validate-story":
                validate_story_gate(root)  # deterministic core; llm review comes before compose
            else:
                thunk()
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"Pre-image gate {name} failed — fix the planning before generating any images "
                f"(don't waste a third-party generation round): {exc}"
            ) from exc


def _character_reference_prompt(root: Path) -> str:
    """Reference prompt from either export path.

    v5.13.0 only read prompts/character-reference.txt while the formal
    export-character-prompts command writes prompts/characters/<id>.md — new
    projects silently lost the step-0 reference (release audit P1-8).
    """
    reference_file = root / "prompts" / "character-reference.txt"
    if reference_file.is_file():
        text = reference_file.read_text(encoding="utf-8").strip()
        if text:
            return text
    characters_dir = root / "prompts" / "characters"
    if characters_dir.is_dir():
        parts = []
        for path in sorted(characters_dir.glob("*.md")):
            content = path.read_text(encoding="utf-8").strip()
            if content:
                parts.append(f"—— 角色 {path.stem} ——\n{content}")
        if parts:
            return "多角色定妆合集（一张图内并排列出所有角色的全身定妆，白底，无文字）：\n\n" + "\n\n".join(parts)
    return ""


def _project_has_characters(root: Path) -> bool:
    try:
        bible = json.loads((root / "planning" / "character_bible.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        return False
    characters = bible.get("characters") if isinstance(bible, dict) else None
    return isinstance(characters, list) and len(characters) > 0


def _has_approved_character_reference(root: Path) -> bool:
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        return False
    return any(
        isinstance(item, dict) and item.get("kind") == "character-reference" and item.get("status") == "approved"
        for item in manifest.get("assets", [])
    )


def _scene_groups(episode: dict[str, Any]) -> list[dict[str, Any]]:
    """[(scene label, [panel indices])] in reading order, for scene-master
    generation ordering in the README."""
    groups: list[dict[str, Any]] = []
    index = 0
    scenes = episode.get("scenes")
    if not isinstance(scenes, list):
        return groups
    for scene_number, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            continue
        panels = [panel for panel in scene.get("panels", []) if isinstance(panel, dict)]
        indices = []
        for _panel in panels:
            index += 1
            indices.append(index)
        if indices:
            label = str(scene.get("scene_id") or scene.get("title") or f"场景{scene_number}")
            groups.append({"label": label, "indices": indices})
    return groups


def prepare_inbox(project_dir: str | Path, episode_id: str | None = None) -> dict[str, Any]:
    """Create tmp/inbox/ with a Chinese checklist and per-panel prompt files.

    Refuses to run before the pre-image homework is done: the full formal
    gate battery (minus image-dependent gates) must pass and compiled prompts
    must exist for every panel.
    """
    root = Path(project_dir)
    episode = load_episode(root)
    episode_id = resolve_episode_id(episode, episode_id)
    panels = _panels(root)
    _run_pre_image_gates(root)
    prompts_manifest = root / "prompts" / "manifest.json"
    if not prompts_manifest.is_file():
        raise FileNotFoundError(
            f"Compiled prompt manifest missing: {prompts_manifest}. Run export-project-prompts first."
        )
    reference_prompt = _character_reference_prompt(root)
    if not reference_prompt and _project_has_characters(root):
        raise FileNotFoundError(
            "No character reference prompt found (prompts/character-reference.txt or prompts/characters/*.md) "
            "but the character bible has characters. Run export-character-prompts first — without a reference "
            "image the cast will drift face-to-face across panels."
        )
    inbox = inbox_dir(root)
    inbox.mkdir(parents=True, exist_ok=True)
    title = _book_title(root)
    declared_aspect, _, example = _aspect_requirement(root)

    custom_style = get_custom_art_style(root)
    items: list[dict[str, Any]] = []
    for index, _panel in enumerate(panels, start=1):
        filename = f"panel-{index:02d}.png"
        prompt = _compiled_prompt(root, index)
        if custom_style and "ART STYLE OVERRIDE" not in prompt:
            prompt = (
                f"ART STYLE OVERRIDE（用户指定画风，最高优先级）：{custom_style}\n"
                "整张图请用这个画风——媒介、线条、色彩、质感都以它为准。\n"
                "原创设计：不要照抄任何现有影视/游戏/漫画作品或在世画师的角色造型——画风按技法特征执行，不是复刻某个具体作品。\n\n"
                + prompt
            )
        (inbox / f"panel-{index:02d}.prompt.txt").write_text(prompt + "\n", encoding="utf-8")
        items.append({"index": index, "filename": filename, "prompt": prompt})

    if reference_prompt:
        (inbox / f"{CHARACTER_REFERENCE_STEM}.prompt.txt").write_text(reference_prompt + "\n", encoding="utf-8")
        # The formal provenance target: inbox-import binds the reference asset
        # to prompts/character-reference.txt, which used to not exist on the
        # fallback path (manifest prompt_sha256 came out empty — release audit
        # v5.13.1 P1-3).
        formal_prompt = root / "prompts" / "character-reference.txt"
        formal_prompt.parent.mkdir(parents=True, exist_ok=True)
        formal_prompt.write_text(reference_prompt + "\n", encoding="utf-8")

    scene_groups = _scene_groups(episode)
    (inbox / README_NAME).write_text(
        _render_readme(title, items, declared_aspect, example, bool(reference_prompt), scene_groups),
        encoding="utf-8",
    )
    return {
        "inbox_dir": str(inbox),
        "episode_id": episode_id,
        "panel_count": len(items),
        "aspect_ratio": declared_aspect,
        "character_reference_prompt": bool(reference_prompt),
        "scene_groups": scene_groups,
        "items": items,
    }


def _scan_inbox_images(inbox: Path, expected_count: int) -> tuple[dict[int, Path], Path | None]:
    """Strict filename contract: exactly panel-01..panel-NN, one file each.

    Natural-sort pairing silently mis-assigned arbitrary filenames to panels
    (audit P1-4f); here anything unexpected is an error, not a guess.
    """
    expected_stems = {f"panel-{index:02d}": index for index in range(1, expected_count + 1)}
    by_index: dict[int, Path] = {}
    reference: Path | None = None
    unexpected: list[str] = []
    for path in sorted(inbox.iterdir()):
        if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        stem = path.stem
        if stem == CHARACTER_REFERENCE_STEM:
            if reference is not None:
                raise ValueError(
                    f"Multiple character reference images found: {reference.name} and {path.name}. Keep exactly one."
                )
            reference = path
            continue
        index = expected_stems.get(stem)
        if index is None:
            unexpected.append(path.name)
            continue
        if index in by_index:
            raise ValueError(
                f"Panel {index:02d} has two files ({by_index[index].name} and {path.name}). Keep exactly one."
            )
        by_index[index] = path
    missing = [f"panel-{index:02d}" for index in range(1, expected_count + 1) if index not in by_index]
    problems = []
    if missing:
        problems.append(f"missing: {', '.join(missing)}")
    if unexpected:
        problems.append(
            f"unexpected image files: {', '.join(unexpected)} (only panel-NN.png/jpg/webp and "
            f"{CHARACTER_REFERENCE_STEM}.* are accepted)"
        )
    if problems:
        raise ValueError(
            f"Inbox file check failed for {inbox}: " + "; ".join(problems) + ". "
            "Fix the filenames exactly as listed in the inbox README, then re-run inbox-import."
        )
    return by_index, reference


def _check_inbox_image(
    path: Path,
    *,
    target_ratio: float | None,
    declared_aspect: str,
    min_file_bytes: int,
) -> None:
    size = path.stat().st_size
    if size < min_file_bytes:
        raise ValueError(f"Image too small: {path.name} ({size} bytes < {min_file_bytes}).")
    # Content-based admission (release audit v5.13.1 P1-6): the inbox is the
    # rawest external input path of all — never trust the extension.
    from .image_safety import open_image_checked

    width, height, _fmt = open_image_checked(path, purpose="inbox image")
    if min(width, height) < MIN_SHORT_SIDE:
        raise ValueError(
            f"Image below minimum resolution: {path.name} ({width}x{height}); short side must be "
            f">= {MIN_SHORT_SIDE}px (aim for {RECOMMENDED_SHORT_SIDE}px)."
        )
    if target_ratio is not None and height:
        ratio = width / height
        if abs(ratio - target_ratio) / target_ratio > ASPECT_TOLERANCE:
            raise ValueError(
                f"Image aspect mismatch: {path.name} is {width}x{height} (ratio {ratio:.3f}), but this "
                f"project delivers {declared_aspect} ({target_ratio:.3f}). Regenerate at {declared_aspect} — "
                "a wrong ratio would be cropped or rejected by the compose aspect gate anyway."
            )


def _next_asset_version(root: Path, asset_id: str) -> int:
    manifest_path = root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        return 1
    versions = [
        int(asset.get("version") or 0)
        for asset in manifest.get("assets", [])
        if isinstance(asset, dict) and asset.get("asset_id") == asset_id
    ]
    return (max(versions) + 1) if versions else 1


def import_inbox(
    project_dir: str | Path,
    episode_id: str | None = None,
    *,
    min_file_bytes: int = DEFAULT_MIN_FILE_BYTES,
) -> dict[str, Any]:
    """Import tmp/inbox/ images as CANDIDATES through the official materializer.

    Nothing is auto-approved (audit P1-4d/e): after import the host inspects
    every candidate image and runs approve-asset / reject-asset per panel,
    exactly like the native generation path.
    """
    from .artifact_materializer import materialize_image

    root = Path(project_dir)
    episode = load_episode(root)
    episode_id = resolve_episode_id(episode, episode_id)
    inbox = inbox_dir(root)
    if not inbox.is_dir():
        raise FileNotFoundError(
            f"Image inbox not found: {inbox}. "
            f"Run `book-to-comic inbox-prepare --project {root}` first, then drop your panel images in."
        )
    panels = _panels(root)
    declared_aspect, target_ratio, _ = _aspect_requirement(root)
    by_index, reference = _scan_inbox_images(inbox, len(panels))

    # Character-consistency hard rule (release audit v5.13.1 P1-2): a cast
    # project used to import, approve and validate straight through with NO
    # character reference at all. Fail closed before touching anything.
    has_characters = _project_has_characters(root)
    if has_characters and reference is None and not _has_approved_character_reference(root):
        raise ValueError(
            "This project has characters but no approved character reference and no "
            f"{CHARACTER_REFERENCE_STEM}.* image in the inbox. 角色一致性硬规则：先出定妆图——把 "
            f"{CHARACTER_REFERENCE_STEM}.png 放进 {inbox} 与 panel 图一起导入（见 inbox README），"
            "或先在原生路径 approve 角色定妆图，再重跑 inbox-import。"
        )

    # Validate EVERYTHING before importing anything.
    for index in sorted(by_index):
        _compiled_prompt(root, index)
        _check_inbox_image(
            by_index[index],
            target_ratio=target_ratio,
            declared_aspect=declared_aspect,
            min_file_bytes=min_file_bytes,
        )

    # Scene-master lineage: from the 2nd panel of a scene on, the panel must
    # reference its scene's first panel (the scene master).
    scene_master_of: dict[int, int] = {}
    for group in _scene_groups(episode):
        indices = group.get("indices") or []
        for position, panel_index in enumerate(indices):
            if position > 0:
                scene_master_of[panel_index] = indices[0]

    imported: list[dict[str, Any]] = []
    if reference is not None:
        reference_prompt_path = root / "prompts" / "character-reference.txt"
        if not reference_prompt_path.is_file():
            inbox_prompt = inbox / f"{CHARACTER_REFERENCE_STEM}.prompt.txt"
            if inbox_prompt.is_file():
                reference_prompt_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(inbox_prompt, reference_prompt_path)
            else:
                raise FileNotFoundError(
                    "Character reference prompt not found (prompts/character-reference.txt). "
                    "Re-run inbox-prepare so the formal prompt exists before importing."
                )
        item = materialize_image(
            project=root,
            kind="character-reference",
            asset_id=CHARACTER_REFERENCE_STEM,
            version=_next_asset_version(root, CHARACTER_REFERENCE_STEM),
            snapshot=inbox,
            prompt=reference_prompt_path,
            source=reference,
            source_mode="manual-inbox",
        )
        imported.append(item)
    for index in sorted(by_index):
        asset_id = f"panel-{index:02d}"
        reference_ids: list[str] = []
        if has_characters:
            reference_ids.append(CHARACTER_REFERENCE_STEM)
        master_index = scene_master_of.get(index)
        if master_index is not None and (master_index in by_index or master_index < index):
            reference_ids.append(f"panel-{master_index:02d}")
        item = materialize_image(
            project=root,
            kind="panel",
            asset_id=asset_id,
            version=_next_asset_version(root, asset_id),
            snapshot=inbox,
            prompt=root / "prompts" / f"panel-{index:02d}.txt",
            panel_index=index,
            reference_assets=reference_ids or None,
            source=by_index[index],
            source_mode="manual-inbox",
        )
        imported.append(item)

    report = {
        "schema_version": "1.0",
        "status": "inbox-candidates-imported",
        "episode_id": episode_id,
        "source_mode": "manual-inbox",
        "panel_count": len(by_index),
        "character_reference_imported": reference is not None,
        "candidates": [
            {
                "asset_id": item["asset_id"],
                "version": item["version"],
                "candidate_path": item["candidate_path"],
            }
            for item in imported
        ],
        "next_steps": (
            "宿主逐张查看 assets/candidates/ 里的候选图（构图/角色一致性/画面质量），"
            "逐个 approve-asset 或 reject-asset；全部 approve 后跑 validate-project-assets 再继续。"
        ),
        "disclosure": "图片为手动导入（manual-inbox），非宿主自动生成；交付摘要会如实披露。",
    }
    qa_dir = root / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    (qa_dir / "inbox-import-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def refine_dir(root: Path) -> Path:
    return root / "tmp" / REFINE_DIRNAME


def prepare_refine(
    project_dir: str | Path,
    panels: list[int] | None = None,
) -> dict[str, Any]:
    """Export approved panels + per-panel refine briefs so the user can polish
    them in any image-to-image tool (Jimeng / Doubao Seedream / Keling ...).

    This is the second-pass quality path: composition and story are already
    approved; the external tool only upgrades rendering quality. Low denoise /
    high reference fidelity, keep composition, characters, and layout unchanged.
    """
    root = Path(project_dir)
    panel_dir = root / "assets" / "panels"
    approved = sorted(panel_dir.glob("*.png"), key=lambda path: path.name)
    if not approved:
        raise FileNotFoundError(
            f"No approved panels in {panel_dir}; refine works on approved panels only."
        )
    all_indexes = [int(path.stem) for path in approved if path.stem.isdigit()]
    targets = sorted(set(panels)) if panels else all_indexes
    unknown = [index for index in targets if index not in all_indexes]
    if unknown:
        raise ValueError(f"Panels not found for refine: {unknown}. Approved panels: {all_indexes}")

    destination = refine_dir(root)
    destination.mkdir(parents=True, exist_ok=True)
    custom_style = get_custom_art_style(root)
    items: list[dict[str, Any]] = []
    for index in targets:
        source = panel_dir / f"{index:02d}.png"
        shutil.copy2(source, destination / f"current-panel-{index:02d}.png")
        brief = _refine_brief(root, index, custom_style)
        (destination / f"panel-{index:02d}.refine.txt").write_text(brief + "\n", encoding="utf-8")
        items.append({"index": index, "filename": f"panel-{index:02d}.png", "brief": brief})
    (destination / REFINE_README_NAME).write_text(_render_refine_readme(_book_title(root), items), encoding="utf-8")
    return {"refine_dir": str(destination), "panel_count": len(items), "items": items}


def import_refine(
    project_dir: str | Path,
    *,
    min_file_bytes: int = DEFAULT_MIN_FILE_BYTES,
) -> dict[str, Any]:
    """Import refined panels from tmp/refine/ as CANDIDATES for re-approval.

    The first cut replaced canonical files at import time and appended
    approved manifest entries with a note saying "host must re-inspect" —
    unreviewed external art with production status, and an injected I/O
    failure mid-commit left canonical/manifest/history disagreeing (2026-07
    release audit P1-3/P1-4). Now refined images ride the SAME materializer as
    everything else: validate all → land as candidates → host inspects each →
    approve-asset supersedes the old version and replaces the canonical. No
    canonical file and no approved status changes at import time, so there is
    nothing to half-commit. The current canonical is snapshotted into
    assets/refine-history/ for rollback before any later approve overwrites it.
    """
    from .artifact_materializer import materialize_image

    root = Path(project_dir)
    source_dir = refine_dir(root)
    if not source_dir.is_dir():
        raise FileNotFoundError(
            f"Refine directory not found: {source_dir}. Run `book-to-comic refine-prepare --project {root}` first."
        )
    declared_aspect, target_ratio, _ = _aspect_requirement(root)
    refined_files: dict[int, Path] = {}
    for path in sorted(source_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        stem = path.stem
        if stem.startswith("current-panel"):
            continue
        if not stem.startswith("panel-") or not stem[len("panel-"):].isdigit():
            raise ValueError(
                f"Unexpected refine image name: {path.name}. Save refined panels exactly as panel-NN.png."
            )
        index = int(stem[len("panel-"):])
        if index in refined_files:
            raise ValueError(f"Panel {index:02d} has two refined files; keep exactly one.")
        refined_files[index] = path
    if not refined_files:
        raise ValueError(
            f"No refined images found in {source_dir}. Save polished images as panel-NN.png "
            "(only the panels you actually refined)."
        )

    panel_dir = root / "assets" / "panels"
    # Validate EVERYTHING before registering anything.
    for index, path in sorted(refined_files.items()):
        canonical = panel_dir / f"{index:02d}.png"
        if not canonical.is_file():
            raise ValueError(f"Refined image {path.name} has no approved panel to replace: {canonical}")
        _check_inbox_image(
            path,
            target_ratio=target_ratio,
            declared_aspect=declared_aspect,
            min_file_bytes=min_file_bytes,
        )

    history_dir = root / "assets" / "refine-history"
    history_dir.mkdir(parents=True, exist_ok=True)
    candidates: list[dict[str, Any]] = []
    for index, path in sorted(refined_files.items()):
        canonical = panel_dir / f"{index:02d}.png"
        version = _next_history_version(history_dir, index)
        history_copy = history_dir / f"{index:02d}-v{version:02d}.png"
        if not history_copy.exists():
            shutil.copy2(canonical, history_copy)
        asset_id = f"panel-{index:02d}"
        item = materialize_image(
            project=root,
            kind="panel",
            asset_id=asset_id,
            version=_next_asset_version(root, asset_id),
            snapshot=source_dir,
            prompt=root / "prompts" / f"panel-{index:02d}.txt",
            panel_index=index,
            source=path,
            source_mode="refine-inbox",
        )
        candidates.append(
            {"asset_id": item["asset_id"], "version": item["version"], "candidate_path": item["candidate_path"]}
        )

    report = {
        "schema_version": "2.0",
        "status": "refine-candidates-imported",
        "candidate_count": len(candidates),
        "candidates": candidates,
        "source_mode": "refine-inbox",
        "next_steps": (
            "宿主逐张对照 assets/candidates/ 里的精修候选与原 approved 版：构图/角色/场景必须一致、只是质感提升；"
            "确认后逐个 approve-asset（会自动 supersede 旧版并替换 canonical），不确认就 reject-asset。"
            "原版已备份在 assets/refine-history/ 可回退。"
        ),
    }
    qa_dir = root / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    (qa_dir / "refine-import-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def _refine_brief(root: Path, index: int, custom_style: str) -> str:
    prompt_path = root / "prompts" / f"panel-{index:02d}.txt"
    original = prompt_path.read_text(encoding="utf-8").strip() if prompt_path.is_file() else ""
    lines = [
        f"第 {index} 格精修指令（image-to-image，垫图 = current-panel-{index:02d}.png）",
        "",
        "硬约束（必须保持不变）：",
        "- 构图、机位、人物位置、动作、表情方向不变；",
        "- 角色长相、发型、服装、体型不变；",
        "- 场景结构、光源方向、关键道具不变；",
        "- 不要在画面里写任何文字/对白/水印。",
        "",
        "精修目标（只提升渲染质量）：",
        "- 线条更干净、五官和手部更准确；",
        "- 光影层次和材质质感更丰富（皮肤/布料/金属/纸张区分开）；",
        "- 色彩更统一、更有氛围；分辨率尽量取工具最高档。",
        "",
        "建议参数：重绘幅度/denoise 取低档（0.2-0.4），参考强度取高档。",
    ]
    if custom_style:
        lines += ["", f"画风锁定：{custom_style}"]
    if original:
        lines += ["", "原始生图提示词（供理解画面内容，不必重跑文生图）：", original]
    return "\n".join(lines)


def _render_refine_readme(title: str, items: list[dict[str, Any]]) -> str:
    count = len(items)
    lines = [
        f"# 精修取图清单（{title}）",
        "",
        "这些格的构图和故事已经定稿，现在只做「二段精修」：用任意 **图生图** 工具",
        "（即梦 / 豆包 Seedream / 可灵等，网页或 App 都行，不需要 API key）把渲染质量拉高。",
        "",
        "操作步骤：",
        "1. 每格用 `current-panel-NN.png` 当垫图/参考图，按 `panel-NN.refine.txt` 里的指令精修；",
        "2. 重绘幅度调低（0.2-0.4），保持构图/角色/场景不变，只提升质感；",
        "3. 精修结果**存回本文件夹**，命名 `panel-NN.png`（只放你精修了的格，不必全量）；",
        f"4. 放好后运行：book-to-comic inbox-import --refine --project <项目目录>（共 {count} 格待精修）。",
        "   导入后进入候选区,由宿主逐张对照原版确认后 approve,不会直接替换成品;",
        "",
        "注意：把图片上传到第三方生图工具前，请确认你有权这么做（版权/隐私），",
        "并了解该工具的条款（数据留存、是否用于训练、商用许可）。",
        "",
        "导入后原版本自动备份到 assets/refine-history/，可随时回退。",
        "",
        "---",
        "",
    ]
    for item in items:
        lines.append(f"## 第 {item['index']} 格 → 精修后存为 `{item['filename']}`")
        lines.append("")
        lines.append("```")
        lines.append(item["brief"])
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def _next_history_version(history_dir: Path, index: int) -> int:
    existing = list(history_dir.glob(f"{index:02d}-v*.png"))
    return len(existing) + 1


def _render_readme(
    title: str,
    items: list[dict[str, Any]],
    declared_aspect: str,
    example_size: str,
    has_reference_prompt: bool,
    scene_groups: list[dict[str, Any]] | None = None,
) -> str:
    count = len(items)
    size_line = f"（例如 {example_size} 或更大）" if example_size else ""
    lines = [
        f"# 把图片放进这个文件夹（{title}）",
        "",
        "这是这一话的「取图清单」。用你顺手的 AI 生图工具（即梦 / 可灵 / 豆包 / Midjourney 等，",
        "网页或手机 App 都行，**不需要 API key**）按下面每一格的提示词生成图片，",
        "下载后**按指定的文件名**存回这个文件夹。",
        "",
        "硬性要求（导入时逐条机器检查，不合格会明确报错）：",
        f"- **画幅比例 {declared_aspect}**：生图时直接选 {declared_aspect} 竖幅{size_line}；比例不对会被拒收；",
        f"- 分辨率：短边至少 {MIN_SHORT_SIDE} 像素，建议 {RECOMMENDED_SHORT_SIDE} 以上；文件不小于 100KB；",
        "- **文件名必须严格是 `panel-01.png` … `panel-NN.png`**（jpg/webp 也行），多余的图或改名的图都会被拒收；",
        "- **不要**让生图工具在画面里写中文 / 对白 / 标题——文字由程序后期统一叠加。",
    ]
    if has_reference_prompt:
        lines += [
            "",
            f"第 0 步（强烈建议）：先用 `{CHARACTER_REFERENCE_STEM}.prompt.txt` 生成一张角色定妆图，",
            f"存回本文件夹命名 `{CHARACTER_REFERENCE_STEM}.png`；之后每一格生图都把它作为参考图/垫图，",
            "角色长相才不会每格都变样。导入时它会一并登记为项目的角色参考资产。",
        ]
    if scene_groups:
        lines += [
            "",
            "**按场景顺序出图（保持空间/光源连贯的关键）**：",
        ]
        for group in scene_groups:
            indices = group["indices"]
            first = indices[0]
            rest = "、".join(str(i) for i in indices[1:]) if len(indices) > 1 else ""
            line = f"- {group['label']}：先生成第 {first} 格（本场首格 = scene master）"
            if rest:
                line += f"，第 {rest} 格生图时**同时垫**角色参考图 + 第 {first} 格的成图，锁定同场景的空间结构和光源方向。"
            lines.append(line)
    lines += [
        "",
        "隐私与授权提醒：把提示词/参考图上传到第三方生图工具前，请确认你有权这么做，",
        "并了解该工具的条款（数据留存、是否用于训练、商用许可）。",
        "",
        f"放齐全部 {count} 张后，回到对话说一句「图放好了」，或自己运行：",
        "",
        "    book-to-comic inbox-import --project <你的项目目录>",
        "",
        "导入后图片先进入 assets/candidates/ 候选区，由宿主逐张看图质检后 approve，",
        "和自动生图走同一套审批流程（不会因为尺寸合格就自动算通过）。",
        "",
        "（每格的提示词也单独存成了 panel-NN.prompt.txt，方便复制。）",
        "",
        "---",
        "",
    ]
    for item in items:
        lines.append(f"## 第 {item['index']} 格 → 存为 `{item['filename']}`")
        lines.append("")
        lines.append("提示词：")
        lines.append("")
        lines.append("```")
        lines.append(item["prompt"])
        lines.append("```")
        lines.append("")
    return "\n".join(lines)
