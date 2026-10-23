from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import zipfile
from typing import Any

from PIL import Image

from .composer import compose_carousel_card_images, compose_long_image, create_contact_sheet
from .delivery import export_cards_delivery
from .delivery_gate import is_artifact_project
from .models import AdaptationPackage, Character, CoreIdea, Panel, Suitability
from .narrative_identity import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, empty_narrative_identity
from .project_layout import load_episode, new_episode_skeleton, save_episode
from .text_bible import normalize_story_panel_for_package
from .visual_identity import empty_visual_identity
from .vector_renderer import render_vector_episode


DEFAULT_EPISODE_ID = "EP01"


def extract_book_to_project(
    input_path: str | Path,
    output_dir: str | Path,
    *,
    language: str = DEFAULT_LANGUAGE,
    force: bool = False,
) -> Path:
    source_file = Path(input_path)
    if not source_file.exists():
        raise FileNotFoundError(f"Input book file does not exist: {source_file}")
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError(f"language must be one of {', '.join(SUPPORTED_LANGUAGES)}")

    project_dir = Path(output_dir)
    # Same protection as init-project (audit P1-1): extract used to silently
    # reset manifest/state/episode of a live project with exit 0.
    markers = [
        project_dir / "project.json",
        project_dir / "manifest.json",
        project_dir / "state.json",
        project_dir / "story" / "episode-001.json",
    ]
    existing = [path for path in markers if path.exists()]
    # ANY non-empty target refuses by default — marker-only checks let stray
    # private files get mixed into the fresh project (release audit v5.13.2 P1-2).
    strays = [child for child in sorted(project_dir.iterdir()) if child.name != "backup"] if project_dir.is_dir() else []
    if existing or strays:
        if not force:
            found = ", ".join(path.name for path in existing) if existing else ", ".join(c.name for c in strays[:5])
            raise FileExistsError(
                f"{project_dir} is not empty ({found}). extract never mixes into existing content. "
                "Pick a fresh directory, or re-run with --force to start clean (EVERYTHING there is "
                "moved to backup/extract-<timestamp>/ first)."
            )
        # Move the whole old tree, not four marker files — a partial backup
        # left old source/planning mixed into the new project (release audit P1-2).
        from .artifact_materializer import _unique_backup_dir

        stamp_dir = _unique_backup_dir(project_dir / "backup", "extract")
        for child in sorted(project_dir.iterdir()):
            if child.name == "backup":
                continue
            shutil.move(str(child), str(stamp_dir / child.name))
    project_dir.mkdir(parents=True, exist_ok=True)
    source_dir = project_dir / "source"
    planning_dir = project_dir / "planning"
    story_dir = project_dir / "story"
    for directory in (
        source_dir,
        planning_dir,
        story_dir,
        project_dir / "prompts",
        project_dir / "text-prompts",
        project_dir / "assets",
        project_dir / "qa",
        project_dir / "review",
        project_dir / "final",
        project_dir / "final" / "cover",
        project_dir / "tmp",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    text = _extract_text(source_file)
    chapters = _chapters_from_text(text)
    slug = _slug(source_file.stem)
    title = source_file.stem
    now = _now()

    _write_json(project_dir / "project.json", _project_json(slug, title, now, language=language))
    _write_json(project_dir / "manifest.json", {"schema_version": "2.0", "project_id": slug, "assets": []})
    _write_json(project_dir / "state.json", {"schema_version": "2.0", "status": "initialized", "updated_at": now})
    (source_dir / "raw_text.txt").write_text(text, encoding="utf-8")
    _write_json(source_dir / "chapters.json", chapters)
    _write_json(source_dir / "metadata.json", _metadata_json(source_file, title, now, language=language))
    _write_json(source_dir / "extraction_report.json", _extraction_report_json(source_file, text, chapters))
    _write_json(source_dir / "source_manifest.json", _source_manifest_json(source_file, title, now))

    series_bible = _empty_series_bible_json(title, chapters)
    character_bible = _empty_character_bible_json()
    environment_bible = _empty_environment_bible_json()
    style_bible = _empty_style_bible_json()
    visual_identity = empty_visual_identity(book_title=title)
    narrative_identity = empty_narrative_identity(book_title=title, language=language)
    _write_json(planning_dir / "series_bible.json", series_bible)
    _write_json(planning_dir / "character_bible.json", character_bible)
    _write_json(planning_dir / "environment_bible.json", environment_bible)
    _write_json(planning_dir / "style_bible.json", style_bible)
    _write_json(planning_dir / "visual_identity.json", visual_identity)
    _write_json(planning_dir / "narrative_identity.json", narrative_identity)

    episode = _pending_episode_json(title, chapters)
    save_episode(project_dir, episode)
    return project_dir


def validate_project(project_dir: str | Path) -> list[str]:
    root = Path(project_dir)
    required = [
        "project.json",
        "manifest.json",
        "state.json",
        "source/raw_text.txt",
        "source/chapters.json",
        "source/metadata.json",
        "source/extraction_report.json",
        "source/source_manifest.json",
        "planning/series_bible.json",
        "planning/character_bible.json",
        "planning/environment_bible.json",
        "planning/style_bible.json",
        "planning/visual_identity.json",
        "planning/narrative_identity.json",
        "story/episode-001.json",
    ]
    errors = [f"missing {relative}" for relative in required if not (root / relative).exists()]
    if errors:
        return errors

    try:
        story_episode = load_episode(root)
        character_bible = _read_json(root / "planning" / "character_bible.json")
        environment_bible = _read_json(root / "planning" / "environment_bible.json")
        visual_identity = _read_json(root / "planning" / "visual_identity.json")
        narrative_identity = _read_json(root / "planning" / "narrative_identity.json")
        if story_episode.get("planning_status") == "needs_host_planning":
            errors.append("story.episode-001 planning_status is needs_host_planning")
        if not story_episode.get("scenes"):
            errors.append("story.episode-001.scenes must be planned by host")
        if "panels" in story_episode and story_episode.get("panels") == []:
            errors.append("story.episode-001 must not use root panels: [] as a planning placeholder")
        if not character_bible.get("characters"):
            errors.append("planning.character_bible.characters must be planned by host")
        if not environment_bible.get("environments"):
            errors.append("planning.environment_bible.environments must be planned by host")
        if visual_identity.get("planning_status") == "needs_host_planning":
            errors.append("planning.visual_identity planning_status is needs_host_planning")
        if narrative_identity.get("planning_status") == "needs_host_planning":
            errors.append("planning.narrative_identity planning_status is needs_host_planning")
        if story_episode.get("planning_status") == "needs_host_planning":
            return errors
    except (OSError, ValueError, json.JSONDecodeError, TypeError) as exc:
        errors.append(f"invalid project JSON: {exc}")
    return errors


def render_project(project_dir: str | Path, image_backend: str = "auto") -> list[Path]:
    if image_backend == "external-api":
        raise ValueError("external-api requires an explicit optional integration command")
    if image_backend in ("auto", "vector"):
        backend = "vector"
    elif image_backend == "host-image":
        raise ValueError(
            "host-image is executed by the Codex/Claude host image tool, not by Python. "
            "Generate accepted artwork with the host, save it to a folder, then run "
            "`book-to-comic import-host-images <project> --image-dir <folder>`."
        )
    elif image_backend == "local-model":
        raise ValueError("local-model requires an installed local image workflow integration")
    else:
        raise ValueError(f"Unsupported image backend: {image_backend}")

    root = Path(project_dir)
    errors = validate_project(root)
    if errors:
        raise ValueError("; ".join(errors))

    panels_dir = root / "assets" / "panels"
    episode_path = root / "story" / "episode-001.json"
    paths = render_vector_episode(episode_path, panels_dir)

    episode = load_episode(root)
    panels = _episode_panels(episode)
    assets = []
    for panel, path in zip(panels, paths):
        relative = path.relative_to(root).as_posix()
        panel["asset_path"] = relative
        panel["status"] = "rendered"
        panel["image_backend"] = backend
        assets.append(
            {
                "panel_id": panel["panel_id"],
                "backend": backend,
                "quality_tier": "draft-fallback",
                "path": relative,
                "prompt": panel["image_prompt"],
                "status": "rendered",
                "redo_count": 0,
            }
        )
    save_episode(root, episode)
    _write_episode_prompt_files(root, episode)
    _write_json(
        root / "assets" / "panel_assets.json",
        {
            "schema_version": "1.0",
            "backend": backend,
            "quality_tier": "draft-fallback",
            "assets": assets,
        },
    )
    _write_json(
        root / "manifest.json",
        {
            "schema_version": "1.0",
            "backend": backend,
            "quality_tier": "draft-fallback",
            "assets": assets,
        },
    )
    _write_json(root / "qa" / "qa_report.json", _qa_report("rendered", episode))
    return paths


def compose_project(project_dir: str | Path) -> dict[str, Path]:
    root = Path(project_dir)
    if is_artifact_project(root):
        raise ValueError(
            "This is a gated artifact project: use `compose-project`, which runs the "
            "story, text and lettering gates before writing final/. `compose` is the "
            "ungated legacy path for demo and quick runs."
        )
    panels_dir = root / "assets" / "panels"
    cards_dir = root / "final" / "cards"
    deliverables = root / "final"
    qa_dir = root / "qa"
    deliverables.mkdir(parents=True, exist_ok=True)
    qa_dir.mkdir(parents=True, exist_ok=True)

    package = load_episode_package(root)
    long_image = compose_long_image(
        package,
        deliverables / "long-image.png",
        panel_dir=panels_dir,
        width=1080,
        require_panels=True,
    )
    cards = compose_carousel_card_images(package, panels_dir, cards_dir, width=1080, height=1440)
    contact = create_contact_sheet(panels_dir, package.storyboard, deliverables / "review-contact-sheet.png")

    qa = _qa_report("composed", load_episode(root))
    _write_json(qa_dir / "qa_report.json", qa)
    return {"long_image": long_image, "cards_dir": cards_dir, "review_contact_sheet": contact, "first_card": cards[0]}


def export_project(project_dir: str | Path, formats: str = "pdf,cbz,epub,long-image,zip") -> dict[str, Path]:
    root = Path(project_dir)
    cards_dir = root / "final" / "cards"
    if not cards_dir.exists() or not list(cards_dir.glob("*.png")):
        compose_project(root)

    deliverables = root / "final"
    deliverables.mkdir(parents=True, exist_ok=True)
    requested = {item.strip().lower() for item in formats.split(",") if item.strip()}
    results: dict[str, Path] = {}

    if "pdf" in requested:
        results["pdf"] = export_cards_delivery(cards_dir, deliverables / "comic.pdf", "pdf", title=_project_title(root))
    if "cbz" in requested:
        results["cbz"] = export_cards_delivery(cards_dir, deliverables / "comic.cbz", "cbz", title=_project_title(root))
    if "epub" in requested:
        results["epub"] = export_cards_delivery(cards_dir, deliverables / "comic.epub", "epub", title=_project_title(root), language=_project_language(root))
    if "long-image" in requested and not (deliverables / "long-image.png").exists():
        compose_project(root)
    if "long-image" in requested:
        results["long-image"] = deliverables / "long-image.png"
    if "cards" in requested:
        results["cards"] = cards_dir
    if "zip" in requested or "zip-production" in requested:
        results["zip"] = write_project_production_zip(root, deliverables / "production-debug.zip")
    return results


def write_project_production_zip(project_dir: str | Path, output_path: str | Path) -> Path:
    """LEGACY full-workspace archive — DEBUG bundle, never a public artifact.

    This zip includes source/, planning/ and prompts/ (the raw, possibly
    copyrighted book text and internal prompts). v5.12 wrote it as
    "production.zip", one filename away from being shared as the public
    bundle (audit P0-5). It now names itself production-debug.zip and says
    what it is; the shareable bundle is compose-project's production.zip.
    """
    root = Path(project_dir)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    readme = _production_readme(root)
    manifest = {
        "schema_version": "1.0",
        "format": "production-debug.zip",
        "bundle": "debug",
        "content_warning": (
            "Contains raw source text, planning files and prompts. Do NOT share publicly; "
            "the shareable bundle is final/production.zip from compose-project."
        ),
        "project": _project_title(root),
        "paths_are_relative": True,
        "created_at": _now(),
    }
    include_patterns = [
        "project.json",
        "manifest.json",
        "state.json",
        "source/*",
        "planning/*",
        "story/episode-001.json",
        "prompts/*.txt",
        "text-prompts/*.md",
        "assets/panel_assets.json",
        "assets/panels/*.png",
        "final/cards/*.png",
        "qa/*.json",
        "final/comic.pdf",
        "final/comic.cbz",
        "final/comic.epub",
        "final/long-image.png",
        "final/review-contact-sheet.png",
    ]
    files: list[Path] = []
    for pattern in include_patterns:
        files.extend(path for path in root.glob(pattern) if path.is_file())
    files = _dedupe_preserve_order(files)
    manifest["files"] = [path.relative_to(root).as_posix() for path in files]

    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        archive.writestr("README.md", readme)
        for path in files:
            archive.write(path, path.relative_to(root).as_posix())
    return output


def load_episode_package(project_dir: str | Path) -> AdaptationPackage:
    root = Path(project_dir)
    episode = load_episode(root)
    characters = _read_json(root / "planning" / "character_bible.json")["characters"]
    panels = _episode_panels(episode)
    return AdaptationPackage(
        book_title=episode["book_title"],
        author=episode.get("author", ""),
        episode_title=episode["episode_title"],
        suitability=Suitability(True, "host-native-project", "Project was extracted into a validated episode package."),
        covered_points=tuple(episode.get("covered_points", ())),
        core_ideas=(
            CoreIdea(
                title="本话主旨",
                kernel=episode["primary_thesis"],
                dramatization="用一个具体选择把抽象主题变成可见行动。",
            ),
        ),
        methods=("series-first", "plain-language overlay", "vector fallback"),
        light_shell="现实处境",
        hard_core=episode["primary_thesis"],
        characters=tuple(
            Character(
                name=item["name"],
                concept=item["role"],
                visual=item["visual"],
                personality=item["personality"],
                prompt_fragment=item["prompt_fragment"],
            )
            for item in characters
        ),
        character_relationship=_character_relationship_summary(_read_json(root / "planning" / "character_bible.json")),
        storyboard=tuple(_panel_from_episode_item(item) for item in panels),
        title_candidates=tuple(episode.get("title_candidates", ("书变漫画",))),
        style_id=episode.get("style_id", "editorial"),
    )


def _panel_from_episode_item(item: dict[str, object]) -> Panel:
    normalized = normalize_story_panel_for_package(item)
    return Panel(
        index=int(normalized["index"]),
        beat=str(normalized["beat"]),
        visual=str(normalized["visual"]),
        dialogue=tuple(normalized.get("dialogue", ())),
        narration=str(normalized.get("narration", "")),
        comment_hook=str(normalized.get("comment_hook", "")),
        scene_setting=str(normalized.get("scene_setting", "")),
        interior_monologue=str(normalized.get("interior_monologue", "")),
        connective_prose=str(normalized.get("connective_prose", "")),
        reality_mapping=str(normalized.get("reality_mapping", "")),
        card_copy=tuple(normalized.get("card_copy", ())),
        long_copy=tuple(normalized.get("long_copy", ())),
        invented_dialogue=tuple(normalized.get("invented_dialogue", ())),
        visual_weight=str(item.get("visual_weight") or "normal"),
        layout_hint=str(item.get("layout_hint") or "normal"),
        beat_duration=str(item.get("beat_duration") or "normal"),
        visual_density=str(item.get("visual_density") or "medium"),
        text_density=str(item.get("text_density") or "medium"),
        reveal_priority=str(item.get("reveal_priority") or "normal"),
        pause_after=bool(item.get("pause_after", False)),
        emotional_anchor=bool(item.get("emotional_anchor", False)),
        anchor_subject=str(item.get("anchor_subject") or ""),
        anchor_note=str(item.get("anchor_note") or ""),
        hook_type=str(item.get("hook_type") or ""),
        hook_line=str(item.get("hook_line") or ""),
        is_cover_source=bool(item.get("is_cover_source", False)),
    )


def _episode_panels(episode: dict[str, object]) -> list[dict[str, object]]:
    scenes = episode.get("scenes")
    if not isinstance(scenes, list):
        return []
    panels: list[dict[str, object]] = []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        scene_panels = scene.get("panels")
        if not isinstance(scene_panels, list):
            continue
        panels.extend(panel for panel in scene_panels if isinstance(panel, dict))
    return panels


def _write_episode_prompt_files(root: Path, episode: dict[str, object]) -> None:
    prompt_dir = root / "prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    panels = _episode_panels(episode)
    (prompt_dir / "00-character-reference.txt").write_text(
        "Use the project character_bible.json as the visual contract. Do not render readable text inside panel art.\n",
        encoding="utf-8",
    )
    for index, panel in enumerate(panels, start=1):
        if not isinstance(panel, dict):
            continue
        content = (
            f"Panel: {panel.get('panel_id', f'P{index:02d}')}\n"
            f"Source refs: {', '.join(str(item) for item in panel.get('source_refs', []))}\n"
            f"Image prompt: {panel.get('image_prompt', '')}\n"
            f"Negative prompt: {panel.get('negative_prompt', '')}\n"
            "Text handling: no readable text, letters, numbers, prices, equations, or pseudo-text in the generated image.\n"
        )
        (prompt_dir / f"{index:02d}-panel.txt").write_text(content, encoding="utf-8")


def _character_relationship_summary(character_bible: dict[str, object]) -> str:
    relationships = character_bible.get("relationship_map", [])
    if isinstance(relationships, list) and relationships:
        return "; ".join(
            str(item.get("relationship", "")).strip()
            for item in relationships
            if isinstance(item, dict) and str(item.get("relationship", "")).strip()
        )
    return "角色关系来自 character_bible.json。"


def _extract_text(source_file: Path) -> str:
    suffix = source_file.suffix.lower()
    if suffix in (".txt", ".md", ".markdown"):
        return source_file.read_text(encoding="utf-8")
    if suffix == ".docx":
        try:
            from docx import Document  # type: ignore
        except ImportError as exc:
            raise ValueError("DOCX extraction needs python-docx installed in the local environment") from exc
        document = Document(str(source_file))
        return "\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip())
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader  # type: ignore
        except ImportError as exc:
            raise ValueError("PDF text extraction needs pypdf installed in the local environment") from exc
        reader = PdfReader(str(source_file))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        if not text.strip():
            raise ValueError("PDF has no text layer; use host visual/OCR capability before extraction")
        return text
    if suffix == ".epub":
        raise ValueError("EPUB extraction is reserved for the skill host or an installed EPUB parser")
    raise ValueError(f"Unsupported input format: {suffix}")


def _chapters_from_text(text: str) -> list[dict[str, object]]:
    lines = [line.strip() for line in text.splitlines()]
    chapters: list[dict[str, object]] = []
    current_title = "正文"
    current_lines: list[str] = []
    char_cursor = 0
    start_char = 0

    def flush() -> None:
        nonlocal start_char
        body = "\n".join(line for line in current_lines if line).strip()
        if not body:
            return
        index = len(chapters) + 1
        end_char = start_char + len(body)
        chapters.append(
            {
                "id": f"chapter_{index}",
                "index": index,
                "title": current_title,
                "text": body,
                "start_char": start_char,
                "end_char": end_char,
            }
        )
        start_char = end_char

    for line in lines:
        is_heading = line.startswith("#") or line.startswith("第") and ("章" in line[:8] or "节" in line[:8])
        if is_heading and current_lines:
            flush()
            current_lines = []
            current_title = line.lstrip("#").strip()
            char_cursor += len(line) + 1
            start_char = char_cursor
        elif is_heading:
            current_title = line.lstrip("#").strip()
            char_cursor += len(line) + 1
            start_char = char_cursor
        else:
            current_lines.append(line)
            char_cursor += len(line) + 1
    flush()
    if not chapters:
        body = text.strip()
        chapters.append({"id": "chapter_1", "index": 1, "title": "正文", "text": body, "start_char": 0, "end_char": len(body)})
    return chapters


def _project_json(slug: str, title: str, now: str, *, language: str = DEFAULT_LANGUAGE) -> dict[str, object]:
    return {
        "schema_version": "3.0",
        "project_id": slug,
        "project_title": title,
        "language": language,
        "target_platform": "multi",
        "delivery_intent": "hardcore_showcase",
        "image_backend": "auto",
        "episodes": [DEFAULT_EPISODE_ID],
        "created_at": now,
        "runtime": "host-native-skill",
    }


def _metadata_json(source_file: Path, title: str, now: str, *, language: str = DEFAULT_LANGUAGE) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "title": title,
        "author": "",
        "language": language,
        "source_filename": source_file.name,
        "extracted_at": now,
    }


def _extraction_report_json(source_file: Path, text: str, chapters: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "input_filename": source_file.name,
        "format": source_file.suffix.lower().lstrip(".") or "txt",
        "character_count": len(text),
        "chapter_count": len(chapters),
        "ocr_used": False,
        "warnings": [],
    }


def _source_manifest_json(source_file: Path, title: str, now: str) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "knowledge_only": False,
        "sources": [
            {
                "title": title,
                "url": "",
                "publisher": "",
                "accessed_at": now,
                "source_type": "uploaded_file",
                "reliability": "primary",
                "supports": ["book_identity", "chapter_structure", "episode_EP01"],
                "notes": f"Local uploaded file: {source_file.name}",
            }
        ],
    }


def _empty_series_bible_json(title: str, chapters: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "planning_status": "needs_host_planning",
        "book_title": title,
        "source_chapters": [
            {
                "id": str(chapter.get("id", "")),
                "index": chapter.get("index"),
                "title": str(chapter.get("title", "")),
            }
            for chapter in chapters
        ],
        "arcs": [],
        "episodes": [],
        "host_planning_required": [
            "chapter-aware episode segmentation",
            "book-specific adaptation strategy",
            "book-specific visual identity",
        ],
    }


def _empty_character_bible_json() -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "planning_status": "needs_host_planning",
        "level": "unplanned",
        "characters": [],
        "relationship_map": [],
        "host_planning_required": [
            "book-specific role architecture",
            "silhouette, body, wardrobe and prop locks",
            "relationship engine that fits the source",
        ],
    }


def _empty_environment_bible_json() -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "planning_status": "needs_host_planning",
        "environments": [],
        "host_planning_required": [
            "era and geography",
            "environment categories",
            "recurring location anchors",
        ],
    }


def _empty_style_bible_json() -> dict[str, object]:
    return {
        "schema_version": "2.0",
        "planning_status": "needs_host_planning",
        "style_id": "",
        "variant_id": "",
        "style_scope": "line, color, medium, lettering grammar only; never character, plot, location or prop reuse",
    }


def _pending_episode_json(title: str, chapters: list[dict[str, object]]) -> dict[str, object]:
    episode = new_episode_skeleton(title, episode_id=DEFAULT_EPISODE_ID)
    episode["source_refs"] = []
    return episode


def _qa_report(status: str, episode: dict[str, object]) -> dict[str, object]:
    panels = _episode_panels(episode)
    warnings = []
    backends = set()
    for panel in panels:
        if not panel.get("source_refs"):
            warnings.append(f"{panel.get('panel_id', '?')} missing source_refs")
        backend = panel.get("image_backend")
        if backend:
            backends.add(str(backend))
    if not backends and status in ("rendered", "composed"):
        backends.add("vector")
    quality_tier = "high" if backends == {"host-image"} else "draft-fallback" if "vector" in backends else "unknown"
    return {
        "schema_version": "1.0",
        "status": status,
        "image_backends": sorted(backends),
        "quality_tier": quality_tier,
        "panel_count": len(panels),
        "warnings": warnings,
        "checks": {
            "has_source_refs": not warnings,
            "no_placeholder_panels": status in ("rendered", "composed"),
            "post_production_lettering": status == "composed",
            "not_vector_fallback": quality_tier == "high",
        },
    }


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _project_title(root: Path) -> str:
    try:
        return _read_json(root / "project.json")["project_title"]
    except (OSError, KeyError, json.JSONDecodeError):
        return root.name


def _project_language(root: Path) -> str:
    try:
        language = str(_read_json(root / "project.json").get("language") or "").strip()
    except (OSError, json.JSONDecodeError):
        return DEFAULT_LANGUAGE
    return language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def _production_readme(root: Path) -> str:
    title = _project_title(root)
    return (
        f"# {title} production package\n\n"
        "This package was exported by the host-native book-to-comic workflow.\n"
        "All paths inside this archive are relative. The default path does not require model API keys.\n"
    )


def _dedupe_preserve_order(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    result: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        result.append(path)
    return result


def _slug(text: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "-" for char in text).strip("-")
    return "-".join(part for part in slug.split("-") if part) or "book-to-comic"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
