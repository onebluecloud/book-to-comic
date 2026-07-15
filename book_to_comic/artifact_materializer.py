from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone
import hashlib
import io
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any
import zipfile

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .fonts import find_cjk_font, load_variant
from .argument_map import validate_argument_map
from .balloons import (
    DEFAULT_LETTERING_MODE,
    BalloonPlan,
    PanelBalloonPlan,
    fit_crop_viewport,
    load_balloon_plan,
    profile_for_style,
    render_panel_overlays,
    resolve_lettering_mode,
    validate_balloon_plan,
)
from .character_qa import validate_character_design
from .conflict_gate import validate_conflict
from .art_style import flat_style_balloon_placement
from .delivery_config import DEFAULT_PANEL_ASPECT_RATIO, validate_panel_aspect_consistency, validate_panel_content_fill
from .delivery_gate import (
    COMPLETION_GUIDANCE,
    COMPLETION_STATE_DELIVERED,
    COMPLETION_STATE_FORCED,
    record_bundle_manifest,
    stamp_delivery,
)
from .appeal import validate_appeal
from .cover import build_cover_assets
from .composer import CARD_THEMES, build_panel_overlay_text, compose_carousel_card_images, compose_long_image
from .delivery import export_cards_delivery
from .fit import validate_fit
from .grounding_qa import evaluate_export_rights, validate_grounding
from .models import AdaptationPackage, Character, CoreIdea, Panel, Suitability
from .narrative_identity import empty_narrative_identity, validate_narrative_identity
from .page_plan import load_page_plan, page_slots, panel_id
from .page_qa import validate_page_plan
from .project_layout import load_episode, new_episode_skeleton, save_episode, validate_episode_id
from .source_claims import validate_source_claims
from .source_fidelity import validate_source_fidelity
from .story_gate import flatten_episode_panels, validate_story_gate
from .text_bible import normalize_story_panel_for_package
from .text_distinctiveness import validate_text_distinctiveness
from .text_qa import validate_lettering_fidelity, validate_text_richness
from .lettering_qa import validate_lettering_layout
from .visual_distinctiveness import validate_distinctiveness
from .visual_contract import validate_visual_contract
from .visual_identity import empty_visual_identity, validate_visual_identity
from .world_qa import validate_world_specificity


SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
MANIFEST_VERSION = "2.0"
# All bundle tier file names; a bundle must never swallow a stale sibling.
_BUNDLE_SIBLING_NAMES = {"production.zip", "production-private.zip", "production-debug.zip"}
MIN_SHORT_SIDE = 768
# Publish-quality target. Below this the asset still passes (768 stays the hard
# floor) but carries a resolution_warning so the host asks the image tool for a
# larger size or runs upscale-assets before final composition.
RECOMMENDED_SHORT_SIDE = 1024

# Asset ids become file names. Anything outside this set risks path tricks —
# the 2026-07 audit walked `asset_id='../../../escaped'` OUT of the project and
# the file was written before the late _rel() call finally errored.
_ASSET_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


def init_project(
    book: str,
    project_dir: str | Path,
    *,
    delivery_intent: str = "hardcore_showcase",
    episode_id: str = "EP01",
    force: bool = False,
) -> Path:
    root = Path(project_dir)
    episode_id = validate_episode_id(episode_id)
    if delivery_intent not in {"mass_traffic", "hardcore_showcase"}:
        raise ValueError("delivery_intent must be mass_traffic or hardcore_showcase")
    # Re-running init on a live project used to silently reset manifest, state
    # and episode to empty with exit 0 (audit P1-1). Refuse by default. --force
    # moves the ENTIRE old project into backup/ first — the first fix backed up
    # only four marker files and left old source/planning/assets mixed into the
    # "fresh" project (2026-07 release audit P1-2: content pollution, privacy
    # residue, stale deliverables).
    markers = [
        root / "project.json",
        root / "manifest.json",
        root / "state.json",
        root / "story" / "episode-001.json",
    ]
    existing = [path for path in markers if path.exists()]
    # ANY non-empty target is refused by default, not just marker files — a
    # directory holding only source/private.txt used to get new project files
    # mixed straight into it (release audit v5.13.2 P1-2).
    strays = [child for child in sorted(root.iterdir()) if child.name != "backup"] if root.is_dir() else []
    if existing or strays:
        if not force:
            found = ", ".join(path.name for path in existing) if existing else ", ".join(c.name for c in strays[:5])
            raise FileExistsError(
                f"{root} is not empty ({found}). init-project never mixes into existing content. "
                "Pick a fresh directory, or re-run with --force to start clean (EVERYTHING there is "
                "moved to backup/init-<timestamp>/ first)."
            )
        stamp_dir = _unique_backup_dir(root / "backup", "init")
        for child in sorted(root.iterdir()):
            if child.name == "backup":
                continue
            shutil.move(str(child), str(stamp_dir / child.name))
    for relative in (
        "source",
        "planning",
        "story",
        "prompts",
        "text-prompts",
        "assets/candidates",
        "assets/references",
        "assets/panels",
        "qa",
        "review",
        "final/cover",
        "final/cards",
        "tmp/capture-snapshots",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)
    project_id = _slug(book)
    now = _now()
    _write_json(
        root / "project.json",
        {
            "schema_version": MANIFEST_VERSION,
            "project_id": project_id,
            "project_title": book,
            "book_title": book,
            "episode_id": episode_id,
            "runtime": "host-native-artifact-materializer",
            "image_mode": "codex-native",
            # Self-describing delivery shape: generation, gates and compose all
            # read these instead of scattering their own defaults.
            "panel_aspect_ratio": DEFAULT_PANEL_ASPECT_RATIO,
            "lettering_mode": "hybrid",
            "delivery_intent": delivery_intent,
            "created_at": now,
        },
    )
    _write_json(root / "manifest.json", {"schema_version": MANIFEST_VERSION, "project_id": project_id, "assets": []})
    _write_json(root / "state.json", {"schema_version": MANIFEST_VERSION, "status": "initialized", "updated_at": now})
    save_episode(root, new_episode_skeleton(book, episode_id=episode_id))
    _write_json(root / "planning" / "visual_identity.json", empty_visual_identity(book_title=book))
    _write_json(root / "planning" / "narrative_identity.json", empty_narrative_identity(book_title=book))
    return root


def required_card_theme(root: Path) -> str:
    """Formal compose refuses to run without an explicit card theme.

    卡片背景主题按书气质三选一(奇观→cinematic,文学名著→gallery,通用→
    editorial)。该字段曾是"缺省 editorial"的建议项:v5.13.3 实跑里规划环节
    漏写,整套卡片静默落到默认白卡——发布给第三方的 skill,品味关键项不允许
    静默兜底(v5.13.4)。草稿链路(quick)不经此处,仍由 composer 缺省 editorial。
    """
    card_theme = None
    project_file = Path(root) / "project.json"
    if project_file.exists():
        try:
            card_theme = json.loads(project_file.read_text(encoding="utf-8")).get("card_theme")
        except (OSError, json.JSONDecodeError, AttributeError):
            card_theme = None
    value = str(card_theme or "").strip().lower()
    if value not in CARD_THEMES:
        raise ValueError(
            "project.json card_theme must be set before formal compose — one of "
            f"{', '.join(CARD_THEMES)} (cinematic=视觉奇观深底, gallery=文学名著画廊装裱, "
            f"editorial=现代白卡通用); got {card_theme!r}. "
            "Set it with: book-to-comic set-card-theme --project <project> --theme <theme>"
        )
    return value


def snapshot_images(output: str | Path) -> Path:
    snapshot_path = Path(output)
    roots = _generated_image_roots()
    snapshot = {
        "schema_version": MANIFEST_VERSION,
        "created_at": _now(),
        "roots": [str(root) for root in roots],
        "files": [_file_record(path, root) for root in roots for path in _iter_image_files(root)],
    }
    _write_json(snapshot_path, snapshot)
    return snapshot_path


def recover_session_image(session: str | Path, output: str | Path) -> Path:
    session_path = Path(session)
    if not session_path.exists():
        raise FileNotFoundError(f"Codex session JSONL is missing: {session_path}")
    latest: tuple[int, str] | None = None
    with session_path.open("r", encoding="utf-8", errors="ignore") as fh:
        for line_no, line in enumerate(fh, start=1):
            if "image_generation_call" not in line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            payload = row.get("payload", {})
            if not isinstance(payload, dict):
                continue
            result = payload.get("result")
            if payload.get("type") == "image_generation_call" and isinstance(result, str) and result:
                latest = (line_no, result)
    if latest is None:
        raise ValueError(f"No image_generation_call result found in session JSONL: {session_path}")
    line_no, encoded = latest
    # Session payloads are external input too (release audit v5.13.2 P1-6):
    # cap the encoded size BEFORE decoding, then admit by real content format,
    # not by whatever the session claims.
    from .image_safety import ALLOWED_FORMATS, MAX_FILE_BYTES, MAX_PIXELS

    if len(encoded) > MAX_FILE_BYTES * 4 // 3 + 4:
        raise ValueError(
            f"image_generation_call result at line {line_no} exceeds the {MAX_FILE_BYTES}-byte image budget."
        )
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"Latest image_generation_call result at line {line_no} is not valid base64") from exc
    # Verify in memory, then temp-write + atomic replace: writing the target
    # first meant a corrupt payload destroyed an existing good output before
    # verify() ever ran (audit P2-3).
    with Image.open(io.BytesIO(data), formats=list(ALLOWED_FORMATS)) as image:
        if image.size[0] * image.size[1] > MAX_PIXELS:
            raise ValueError(
                f"session image is {image.size[0]}x{image.size[1]} — over the {MAX_PIXELS}px budget."
            )
        image.verify()
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(output_path.name + ".tmp")
    temp_path.write_bytes(data)
    os.replace(temp_path, output_path)
    return output_path


def materialize_image(
    *,
    project: str | Path,
    kind: str,
    asset_id: str,
    version: int,
    snapshot: str | Path,
    prompt: str | Path,
    panel_index: int | None = None,
    reference_assets: list[str] | None = None,
    source: str | Path | None = None,
    min_short_side: int = MIN_SHORT_SIDE,
    source_mode: str | None = None,
) -> dict[str, object]:
    root = Path(project)
    _require_project(root)
    if kind not in {"character-reference", "panel"}:
        raise ValueError("kind must be character-reference or panel")
    if kind == "panel" and not panel_index:
        raise ValueError("--panel-index is required for panel assets")
    if kind == "panel":
        _require_visual_contract_gate(root, int(panel_index))
    if not _ASSET_ID_RE.fullmatch(str(asset_id)):
        raise ValueError(
            "asset_id may only contain letters, digits, dot, dash and underscore "
            f"(max 64 chars, no path separators): {asset_id!r}"
        )
    source_path = Path(source) if source else _discover_single_new_image(Path(snapshot))
    source_path = _wait_for_stable_file(source_path)
    candidates_dir = root / "assets" / "candidates"
    output_path = candidates_dir / f"{asset_id}-v{version}.png"
    # Belt and braces: the write must stay inside assets/candidates even if the
    # id rule ever loosens — and the check runs BEFORE mkdir/write.
    if not output_path.resolve().is_relative_to(candidates_dir.resolve()):
        raise ValueError(f"asset output path escapes assets/candidates: {output_path}")
    # Asset history is append-only (release audit v5.13.2 P0-4): re-using a
    # version silently erased the rejected/approved record it replaced, which
    # made "reject → replay same version → approve" a legal laundering path.
    existing_versions = sorted(
        int(asset.get("version") or 0)
        for asset in _manifest(root).get("assets", [])
        if isinstance(asset, dict) and asset.get("asset_id") == asset_id
    )
    if int(version) in existing_versions:
        raise ValueError(
            f"Version {version} of {asset_id!r} already exists ({'rejected/approved history is immutable'}). "
            f"Materialize version {existing_versions[-1] + 1} instead."
        )
    expected_version = (existing_versions[-1] + 1) if existing_versions else 1
    if int(version) != expected_version:
        raise ValueError(
            f"Asset versions are strictly sequential: next version of {asset_id!r} is {expected_version}, got {version}."
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = _normalize_png(source_path, output_path, min_short_side=min_short_side)
    prompt_path = Path(prompt)
    prompt_sha = _sha256(prompt_path) if prompt_path.exists() else ""
    item = {
        "asset_id": asset_id,
        "version": version,
        "kind": kind,
        "status": "candidate",
        "panel_index": panel_index,
        "candidate_path": _rel(root, output_path),
        "canonical_path": "",
        "source_mode": source_mode or ("explicit-source" if source else "snapshot-discovery"),
        "source_filename": source_path.name,
        "prompt_path": _rel(root, prompt_path) if prompt_path.resolve().is_relative_to(root.resolve()) else prompt_path.name,
        "prompt_sha256": prompt_sha,
        "reference_asset_ids": reference_assets or [],
        # Honest lineage semantics (release audit v5.13.2 P1-1): these IDs are
        # what the pipeline PLANNED/declared as references. No third-party
        # image tool returns a receipt proving they were actually fed in, so
        # they must never be presented as verified provenance.
        "reference_provenance": "declared" if reference_assets else "",
        "width": width,
        "height": height,
        "format": "png",
        "file_size": output_path.stat().st_size,
        "sha256": _sha256(output_path),
        "created_at": _now(),
    }
    if min(width, height) < RECOMMENDED_SHORT_SIDE:
        item["resolution_warning"] = (
            f"short side {min(width, height)}px is below the publish target {RECOMMENDED_SHORT_SIDE}px; "
            "request a larger size from the image tool or run upscale-assets before compose."
        )
    _upsert_asset(root, item)
    _write_state(root, "asset-candidate", asset_id=asset_id)
    return item


def approve_asset(project: str | Path, asset_id: str, qa_summary: str) -> dict[str, object]:
    root = Path(project)
    if not str(qa_summary or "").strip():
        raise ValueError(
            "qa_summary is required: state what was actually inspected (composition/identity/text/quality). "
            "An empty approval is not a review."
        )
    manifest = _manifest(root)
    item = _latest_asset(manifest, asset_id)
    # Legal transitions only (release audit P1-6): a rejected version stays
    # rejected — produce a NEW candidate version and approve that; an already
    # approved version cannot be re-blessed.
    status = str(item.get("status") or "")
    if status != "candidate":
        raise ValueError(
            f"approve-asset requires the latest version of {asset_id!r} to be a candidate; it is {status!r}. "
            + ("Materialize a new version instead of re-approving a rejected one." if status == "rejected" else "")
        )
    candidate = root / str(item["candidate_path"])
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"candidate_path escapes the project directory: {item['candidate_path']!r}")
    if not candidate.exists():
        raise FileNotFoundError(f"Candidate asset is missing: {candidate}")
    # The approval blesses the EXACT bytes that were materialized and QA'd.
    # Without this re-check, swapping the candidate file after materialize
    # promoted the swapped image to canonical while the manifest still carried
    # the old sha (release audit v5.13.2 P0-4).
    actual_candidate_sha = _sha256(candidate)
    recorded_sha = str(item.get("sha256") or "")
    if recorded_sha and actual_candidate_sha != recorded_sha:
        raise ValueError(
            f"Candidate file for {asset_id!r} changed after materialize "
            f"(recorded {recorded_sha[:12]}…, found {actual_candidate_sha[:12]}…). "
            "Re-materialize the new bytes as a NEW version and approve that."
        )
    if item["kind"] == "character-reference":
        canonical = root / "assets" / "references" / "character-reference.png"
    elif item["kind"] == "panel":
        panel_index = int(item["panel_index"])
        canonical = root / "assets" / "panels" / f"{panel_index:02d}.png"
    else:
        raise ValueError(f"Unsupported asset kind: {item['kind']}")
    canonical.parent.mkdir(parents=True, exist_ok=True)
    # Atomic-ish two-file commit: stage the canonical, swap it in, then write
    # the manifest; if the manifest write fails, restore the previous
    # canonical so disk and manifest never disagree (release audit v5.13.2
    # P0-4: fault-injected manifest failure used to leave a mutated canonical
    # under a manifest that still said candidate).
    previous_bytes = canonical.read_bytes() if canonical.exists() else None
    staged = canonical.with_name(canonical.name + ".tmp")
    shutil.copy2(candidate, staged)
    os.replace(staged, canonical)
    item["status"] = "approved"
    item["canonical_path"] = _rel(root, canonical)
    item["approved_at"] = _now()
    item["qa_summary"] = qa_summary
    item["canonical_sha256"] = _sha256(canonical)
    for existing in manifest.get("assets", []):
        if existing is item:
            continue
        if existing.get("asset_id") == item.get("asset_id") and existing.get("status") == "approved":
            existing["status"] = "superseded"
            existing["superseded_at"] = item["approved_at"]
            existing["superseded_by_version"] = item.get("version")
    try:
        _write_manifest(root, manifest)
    except BaseException:
        if previous_bytes is None:
            canonical.unlink(missing_ok=True)
        else:
            canonical.write_bytes(previous_bytes)
        raise
    _write_state(root, "assets-approved", manifest=manifest, asset_id=asset_id)
    return item


def reject_asset(project: str | Path, asset_id: str, qa_summary: str) -> dict[str, object]:
    root = Path(project)
    manifest = _manifest(root)
    item = _latest_asset(manifest, asset_id)
    status = str(item.get("status") or "")
    if status != "candidate":
        raise ValueError(
            f"reject-asset requires the latest version of {asset_id!r} to be a candidate; it is {status!r} "
            "(history is append-only — a settled verdict is not rewritten)."
        )
    item["status"] = "rejected"
    item["rejected_at"] = _now()
    item["qa_summary"] = qa_summary
    _write_manifest(root, manifest)
    _write_state(root, "asset-rejected", manifest=manifest, asset_id=asset_id)
    return item


def _project_expects_character_reference(root: Path) -> bool:
    try:
        bible = json.loads((root / "planning" / "character_bible.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        return False
    characters = bible.get("characters") if isinstance(bible, dict) else None
    return isinstance(characters, list) and len(characters) > 0


def _unique_backup_dir(base: Path, prefix: str) -> Path:
    """A backup generation directory that can never collide or merge.

    Second-level timestamps re-used the same directory when --force ran twice
    within one second, overwriting the first backup's files and nesting trees
    (release audit v5.13.2 P1-2).
    """
    base.mkdir(parents=True, exist_ok=True)
    for counter in range(10_000):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        name = f"{prefix}-{stamp}" if counter == 0 else f"{prefix}-{stamp}-{counter}"
        candidate = base / name
        try:
            candidate.mkdir(exist_ok=False)
            return candidate
        except FileExistsError:
            continue
    raise RuntimeError(f"Could not allocate a unique backup directory under {base}")


def validate_project_assets(project: str | Path) -> dict[str, object]:
    root = Path(project)
    manifest = _manifest(root)
    approved_panels = [item for item in manifest["assets"] if item.get("kind") == "panel" and item.get("status") == "approved"]
    if not approved_panels:
        raise ValueError("No approved panel assets found")
    # Character-consistency backstop (release audit v5.13.1 P1-2): a cast
    # project whose panels were imported/approved without any character
    # reference used to sail through every asset gate.
    if _project_expects_character_reference(root):
        has_reference = any(
            item.get("kind") == "character-reference" and item.get("status") == "approved"
            for item in manifest["assets"]
        )
        if not has_reference:
            raise ValueError(
                "Project has characters but no approved character-reference asset. Generate/import and "
                "approve the character reference first — panels drawn without it cannot hold one face."
            )
    panel_indexes = sorted(int(item["panel_index"]) for item in approved_panels)
    expected = list(range(1, max(panel_indexes) + 1))
    if panel_indexes != expected:
        raise ValueError(f"Approved panel indexes must be contiguous from 1: found {panel_indexes}")
    # Story and assets must agree on the SAME panel count (release audit
    # v5.13.2 P1-5) — contiguous-from-1 alone accepted 6 approved panels for
    # an 8-panel episode.
    try:
        story_panel_count = len(flatten_episode_panels(load_episode(root)))
    except Exception:  # noqa: BLE001 - projects without an episode validate elsewhere.
        story_panel_count = 0
    if story_panel_count and len(approved_panels) != story_panel_count:
        raise ValueError(
            f"Approved panel count ({len(approved_panels)}) does not match the official episode "
            f"({story_panel_count} panels): approve/reject until they agree."
        )
    reports: list[dict[str, object]] = []
    for item in approved_panels:
        canonical = root / str(item["canonical_path"])
        if not canonical.exists():
            raise FileNotFoundError(f"Canonical asset is missing: {canonical}")
        with Image.open(canonical) as image:
            width, height = image.size
            image.verify()
        if _sha256(canonical) != item.get("canonical_sha256"):
            raise ValueError(f"Canonical asset hash mismatch: {canonical}")
        reports.append({"panel_index": int(item["panel_index"]), "path": _rel(root, canonical), "width": width, "height": height})
    return {"schema_version": MANIFEST_VERSION, "panel_count": len(approved_panels), "panels": reports}


def _require_project_visual_contract_gate(root: Path) -> None:
    try:
        validate_visual_identity(root)
        distinctiveness = validate_distinctiveness(root)
        if not distinctiveness.get("passed"):
            raise ValueError("Distinctiveness report did not pass.")
        report = validate_visual_contract(root)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"Visual contract gate failed: {exc}") from exc
    if not report.get("passed"):
        raise ValueError("Visual contract gate failed: qa/visual-contract-report.json did not pass.")


def _require_visual_contract_gate(root: Path, panel_index: int) -> None:
    _require_project_visual_contract_gate(root)
    panel_id = _panel_id_for_index(root, panel_index)
    contract = _read_json(root / "planning" / "visual_contract.json")
    reference_pack = contract.get("reference_pack", {})
    panel_locks = reference_pack.get("panel_locks", {}) if isinstance(reference_pack, dict) else {}
    if panel_id not in panel_locks:
        raise ValueError(f"Visual contract gate failed: missing panel lock for {panel_id}.")


def _panel_id_for_index(root: Path, panel_index: int) -> str:
    try:
        story = load_episode(root)
        panels = flatten_episode_panels(story)
        if 1 <= panel_index <= len(panels):
            panel = panels[panel_index - 1]
            if isinstance(panel, dict) and panel.get("panel_id"):
                return str(panel["panel_id"])
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        pass
    return f"P{panel_index:02d}"


def formal_compose_gates(
    root: Path,
    *,
    schema3: bool,
    expected_panel_count: int | None = None,
) -> tuple[tuple[str, str, Any], ...]:
    """THE gate registry: (stage, name, thunk) for the formal compose battery.

    compose-project, check and inbox-prepare all consume this list — the old
    hand-maintained copies drifted (check missed content-fill and never
    required the llm gate, so check --stage all said all_passed while compose
    refused; 2026-07 release audit P1-5/P0-3).
    """
    if schema3:
        return (
            ("plan", "validate-grounding", lambda: validate_grounding(root, require_profile=True)),
            ("plan", "validate-fit", lambda: validate_fit(root)),
            ("plan", "validate-argument-map", lambda: validate_argument_map(root)),
            ("plan", "validate-source-fidelity", lambda: validate_source_fidelity(root)),
            ("text", "validate-narrative-identity", lambda: validate_narrative_identity(root)),
            ("plan", "validate-character-design", lambda: validate_character_design(root)),
            ("plan", "validate-world-specificity", lambda: validate_world_specificity(root)),
            ("visual", "validate-visual-contract", lambda: _require_project_visual_contract_gate(root)),
            ("assets", "validate-aspect-consistency", lambda: validate_panel_aspect_consistency(root)),
            ("assets", "validate-content-fill", lambda: validate_panel_content_fill(root)),
            ("plan", "validate-conflict", lambda: validate_conflict(root)),
            (
                "plan",
                "validate-story",
                lambda: validate_story_gate(root, require_llm_gate=True, expected_panel_count=expected_panel_count),
            ),
            ("plan", "validate-page-plan", lambda: validate_page_plan(root)),
            ("text", "validate-text-richness", lambda: validate_text_richness(root)),
            ("text", "validate-lettering-fidelity", lambda: validate_lettering_fidelity(root)),
            ("text", "validate-text-distinctiveness", lambda: validate_text_distinctiveness(root)),
            ("text", "validate-lettering-layout", lambda: validate_lettering_layout(root)),
            ("text", "validate-appeal", lambda: validate_appeal(root)),
        )
    return (
        ("plan", "validate-grounding", lambda: validate_grounding(root, require_profile=True)),
        ("visual", "validate-visual-contract", lambda: _require_project_visual_contract_gate(root)),
        ("text", "validate-narrative-identity", lambda: validate_narrative_identity(root)),
        ("text", "validate-source-claims", lambda: validate_source_claims(root)),
        (
            "plan",
            "validate-story",
            lambda: validate_story_gate(root, require_llm_gate=True, expected_panel_count=expected_panel_count),
        ),
        ("text", "validate-text-richness", lambda: validate_text_richness(root)),
        ("text", "validate-text-distinctiveness", lambda: validate_text_distinctiveness(root)),
        ("text", "validate-lettering-layout", lambda: validate_lettering_layout(root)),
        ("assets", "validate-aspect-consistency", lambda: validate_panel_aspect_consistency(root)),
        ("assets", "validate-content-fill", lambda: validate_panel_content_fill(root)),
    )


def formal_gate_names(*, schema3: bool) -> tuple[str, ...]:
    """Names only — for stamps, docs and set-equality tests."""
    return tuple(name for _, name, _ in formal_compose_gates(Path("."), schema3=schema3))


SCHEMA3_DELIVERY_GATES = formal_gate_names(schema3=True)
SCHEMA2_DELIVERY_GATES = formal_gate_names(schema3=False)


def compose_artifact_project(
    project: str | Path,
    *,
    mode: str = "comic-page",
    allow_gate_failures: bool = False,
    forced_reason: str = "",
    debug_bundle: bool = False,
) -> dict[str, Any]:
    if mode not in {"comic-page", "long-scroll", "card", "review"}:
        raise ValueError("mode must be one of comic-page, long-scroll, card, review.")
    root = Path(project)
    asset_report = validate_project_assets(root)
    # Where did the approved artwork come from? manual-inbox / refine-inbox
    # panels must be disclosed in the stamp and delivery summary — "全自动生成"
    # may not be claimed for hand-imported art (audit P1-4g).
    panel_source_modes = sorted(
        {
            str(item.get("source_mode") or "unknown")
            for item in _manifest(root).get("assets", [])
            if isinstance(item, dict) and item.get("kind") == "panel" and item.get("status") == "approved"
        }
    )
    schema3 = _is_schema3_project(root)
    gates = SCHEMA3_DELIVERY_GATES if schema3 else SCHEMA2_DELIVERY_GATES
    gate_error: Exception | None = None
    try:
        _require_formal_gates(root, schema3=schema3, expected_panel_count=int(asset_report["panel_count"]))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
        # Never emit deliverables past a failing gate unless the caller says so out
        # loud -- and when they do, the bypass is stamped, not silent.
        if not allow_gate_failures:
            raise
        gate_error = exc
    final = root / "final"
    cards_dir = final / "cards"
    final.mkdir(parents=True, exist_ok=True)
    package = _artifact_package(root)
    panel_dir = root / "assets" / "panels"
    lettering_mode = _project_lettering_mode(root)
    # A flat style that reads as painterly/watercolor forces external captions:
    # in-art vector balloons look like stickers on that finish. Only auto-switch
    # when the user hasn't explicitly asked for balloons.
    if lettering_mode == DEFAULT_LETTERING_MODE:
        placement = flat_style_balloon_placement(root)
        if placement == "caption":
            lettering_mode = "hybrid"
    balloon_plan = load_balloon_plan(root)
    # lettering_mode=balloon is an explicit promise of in-art balloons. Composing
    # without a plan used to ship caption-only output while still claiming balloon
    # lettering (2026-07 audit F7) — fail loudly instead. hybrid/caption stay valid.
    if balloon_plan is None and _declared_lettering_mode(root) == "balloon":
        raise ValueError(
            "lettering_mode=balloon but story/balloon_plan.json is missing. Write the plan "
            "(list EVERY panel; a silent panel gets an empty balloons[] entry) or set lettering_mode to hybrid/caption."
        )
    if balloon_plan is not None:
        validate_balloon_plan(
            root,
            panel_dialogue=_panel_letterable_lines(package),
            expected_panel_count=len(package.storyboard),
        )
    long_image = compose_long_image(
        package,
        final / "comic-long.png",
        panel_dir=panel_dir,
        width=1080,
        require_panels=True,
        text_mode="long_form",
        rhythm_report_path=root / "qa" / "rhythm-layout-report.json",
        balloon_plan=balloon_plan,
        lettering_mode=lettering_mode,
    )
    card_theme = required_card_theme(root)
    card_paths = compose_carousel_card_images(package, panel_dir, cards_dir, width=1080, height=1440, balloon_plan=balloon_plan, lettering_mode=lettering_mode, card_theme=card_theme)
    comic_pages_dir: Path | None = None
    comic_page_paths: list[Path] = []
    if mode in {"comic-page", "review"}:
        comic_pages_dir = final / "comic-pages"
        comic_page_paths = _compose_comic_page_images(root, package, panel_dir, comic_pages_dir, balloon_plan=balloon_plan, lettering_mode=lettering_mode)
    cover_manifest = build_cover_assets(root)
    pdf = export_cards_delivery(cards_dir, final / "comic.pdf", "pdf", title=package.book_title)
    cbz = export_cards_delivery(cards_dir, final / "comic.cbz", "cbz", title=package.book_title)
    epub = export_cards_delivery(cards_dir, final / "comic.epub", "epub", title=package.book_title)
    # Rights decide the bundle tier. Passing gates makes the WORK finished;
    # only a clean rights declaration makes it SHAREABLE (audit P0-1):
    # public → production.zip; anything unlicensed/unconsented/forced →
    # production-private.zip; --debug-bundle → production-debug.zip.
    rights = evaluate_export_rights(root)
    # Hard-excluded content is refused outright — not downgraded to a private
    # bundle (release audit v5.13.2 P1-4). This backstops the grounding gate
    # for hosts that jump straight to compose.
    if rights.get("hard_exclusion_hits"):
        raise ValueError(
            "content_safety.hard_exclusion_hits is non-empty — hard-excluded content is never composed "
            "or bundled in any tier: " + ", ".join(map(str, rights["hard_exclusion_hits"]))
        )
    if debug_bundle:
        bundle_kind = "debug"
    elif rights["public_export_allowed"] and gate_error is None:
        bundle_kind = "public"
    else:
        bundle_kind = "private"
    bundle_names = {
        "public": "production.zip",
        "private": "production-private.zip",
        "debug": "production-debug.zip",
    }
    bundle_reasons = list(rights["reasons"])
    if gate_error is not None:
        bundle_reasons.append(f"gates were forced past a failure: {gate_error}")
    # Loose finals (PDF/long image/cards) look identical regardless of rights
    # tier — a visible marker file rides along so a private project's outputs
    # can't be mistaken for shareable ones (release audit P1-9). Written
    # before the stamp so it is part of the sealed output manifest.
    private_notice = final / "仅自用-PRIVATE-DO-NOT-SHARE.txt"
    if bundle_kind == "public":
        if private_notice.exists():
            private_notice.unlink()
    else:
        private_notice.write_text(
            "本目录下所有成品（PDF/长图/卡片/EPUB/CBZ）仅限自用，不得公开分享或投稿。\n"
            "原因：\n- " + "\n- ".join(bundle_reasons or ["debug bundle requested"]) + "\n"
            "权利条件满足并重新 compose 后，此文件会自动移除。\n",
            encoding="utf-8",
        )
    # Stamp BEFORE zipping: the production bundle must carry the final delivery
    # state (it used to be zipped first, shipping a stale or absent stamp).
    stamp_delivery(
        root,
        gates=list(gates),
        panel_count=int(asset_report["panel_count"]),
        forced=gate_error is not None,
        forced_reason=str(gate_error) if gate_error is not None else "",
        rights_status=rights["copyright_status"],
        public_export_allowed=bundle_kind == "public",
        rights_reasons=bundle_reasons,
        panel_source_modes=panel_source_modes,
        expected_bundle_name=bundle_names[bundle_kind],
        expected_bundle_tier=bundle_kind,
    )
    # Drop stale sibling bundles so a later rights change can't leave two
    # archives telling different stories about shareability.
    for stale_name in bundle_names.values():
        stale = final / stale_name
        if stale_name != bundle_names[bundle_kind] and stale.exists():
            stale.unlink()
    archive = _write_artifact_production_zip(
        root,
        final / bundle_names[bundle_kind],
        include_debug=debug_bundle,
        bundle_kind=bundle_kind,
        rights_reasons=bundle_reasons,
    )
    # Bind the archive to the delivery record via the sidecar manifest — the
    # stamp is written before the zip (so the zip can carry it) and therefore
    # cannot know the zip's own hash (release audit v5.13.1 P0-2).
    record_bundle_manifest(root, archive, bundle_kind=bundle_kind)
    final_payload: dict[str, Any] = {
        "mode": mode,
        "lettering_mode_effective": lettering_mode,
        "comic_long": _rel(root, long_image),
        "cards_dir": _rel(root, cards_dir),
        "pdf": _rel(root, pdf),
        "cbz": _rel(root, cbz),
        "epub": _rel(root, epub),
        "cover_dir": "final/cover",
        "cover_candidates": [item["file"] for item in cover_manifest.get("candidates", []) if isinstance(item, dict) and item.get("file")],
        "zip": _rel(root, archive),
        "bundle": bundle_kind,
        "public_export_allowed": bundle_kind == "public",
        "rights_reasons": bundle_reasons,
        "panel_source_modes": panel_source_modes,
    }
    if comic_pages_dir is not None:
        final_payload["comic_pages_dir"] = _rel(root, comic_pages_dir)
        final_payload["comic_pages"] = [_rel(root, path) for path in comic_page_paths]
    _write_state(
        root,
        "final-composed",
        manifest=_manifest(root),
        final=final_payload,
    )
    result: dict[str, Any] = {"mode": mode, "long_image": long_image, "cards_dir": cards_dir, "cover_manifest": final / "cover" / "cover-manifest.json", "pdf": pdf, "cbz": cbz, "epub": epub, "zip": archive, "bundle": bundle_kind, "rights_reasons": bundle_reasons, "panel_source_modes": panel_source_modes}
    # Convergence marker so the CLI (and any programmatic caller) can announce a
    # clean stop instead of leaving the agent to invent more work on a passing
    # comic (v5.13.5). Forced/bypassed compose is not a clean delivery.
    result["completion"] = {
        "state": COMPLETION_STATE_FORCED if gate_error is not None else COMPLETION_STATE_DELIVERED,
        "guidance": COMPLETION_GUIDANCE,
    }
    if comic_pages_dir is not None:
        result["comic_pages_dir"] = comic_pages_dir
        result["comic_pages"] = comic_page_paths
    return result


def _declared_lettering_mode(root: Path) -> str | None:
    """The raw lettering_mode the project explicitly declares (None when absent)."""
    try:
        project = _read_json(root / "project.json")
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        return None
    value = project.get("lettering_mode") if isinstance(project, dict) else None
    if isinstance(value, str) and value.strip():
        return value.strip().lower()
    return None


def _project_lettering_mode(root: Path) -> str:
    """Read lettering_mode from project.json, defaulting to in-image balloons."""
    try:
        project = _read_json(root / "project.json")
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        return DEFAULT_LETTERING_MODE
    value = project.get("lettering_mode") if isinstance(project, dict) else None
    return resolve_lettering_mode(value)


def _is_schema3_project(root: Path) -> bool:
    """Classify by the episode's DECLARED schema_version, not by artifact sniffing.

    Sniffing (page_plan/argument_map/world_model presence) demoted exactly the
    broken projects — a 3.0 episode whose planning files were never built slid
    into the smaller schema-2 gate set instead of failing its missing gates
    (2026-07 audit P0-4). The declared version is the only source of truth;
    sniffing survives solely for legacy episodes that predate the field.
    """
    try:
        episode = load_episode(root)
    except FileNotFoundError:
        return False
    # Parse/validation errors PROPAGATE: swallowing them here would demote an
    # invalid 3.0 episode to the smaller legacy gate set (release audit P2-10).
    declared = str(episode.get("schema_version") or "").strip()
    if declared:
        try:
            major = int(declared.split(".", 1)[0])
        except ValueError:
            raise ValueError(
                f"Unrecognized episode schema_version {declared!r}: expected a numeric version "
                "such as 2.0 or 3.0. Refusing to guess a gate set."
            ) from None
        return major >= 3
    return (
        isinstance(episode.get("page_plan"), dict)
        or isinstance(episode.get("pages"), list)
        or (root / "planning" / "argument_map.json").exists()
        or (root / "planning" / "world_model.json").exists()
    )


def _require_formal_gates(root: Path, *, schema3: bool, expected_panel_count: int | None) -> None:
    """Run the shared gate registry, failing loudly with the gate's name."""
    for _stage, name, thunk in formal_compose_gates(root, schema3=schema3, expected_panel_count=expected_panel_count):
        try:
            thunk()
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"Formal gate {name} failed: {exc}") from exc


def _compose_comic_page_images(
    root: Path,
    package: AdaptationPackage,
    panel_dir: Path,
    output_dir: Path,
    balloon_plan: BalloonPlan | None = None,
    lettering_mode: str = DEFAULT_LETTERING_MODE,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    plan = load_page_plan(root)
    pages = plan.get("pages")
    if not isinstance(pages, list) or not pages:
        return []
    page_width = 1600
    page_height = 2200
    fonts = _comic_page_fonts()
    story = load_episode(root)
    story_panels = [panel for panel in flatten_episode_panels(story) if isinstance(panel, dict)]
    panel_index_by_id = {panel_id(panel, index): index for index, panel in enumerate(story_panels, start=1)}
    panel_by_id = {
        panel_ref: package.storyboard[index - 1]
        for panel_ref, index in panel_index_by_id.items()
        if 0 <= index - 1 < len(package.storyboard)
    }
    paths: list[Path] = []
    for page_index, page in enumerate(pages, start=1):
        if not isinstance(page, dict):
            continue
        slots = page_slots(page)
        if not slots:
            continue
        image = Image.new("RGB", (page_width, page_height), (246, 242, 234))
        draw = ImageDraw.Draw(image)
        _draw_page_header(draw, page, package, page_index, fonts, page_width)
        rects = _comic_page_rects(str(page.get("layout_template") or "four-grid"), len(slots), page_width, page_height)
        for slot, rect in zip(slots, rects):
            panel_ref = str(slot.get("panel_id") or "")
            panel = panel_by_id.get(panel_ref)
            index = panel_index_by_id.get(panel_ref)
            if panel is None or index is None:
                continue
            panel_path = panel_dir / f"{index:02d}.png"
            plan_panel = balloon_plan.by_index.get(index) if balloon_plan else None
            paragraphs = _comic_page_caption_paragraphs(panel, plan_panel, lettering_mode)
            _draw_comic_page_panel(
                image,
                draw,
                panel_path,
                rect,
                paragraphs,
                fonts,
                style_id=package.style_id,
                plan_panel=plan_panel,
                lettering_mode=lettering_mode,
            )
        path = output_dir / f"page-{page_index:02d}.png"
        image.save(path, "PNG")
        paths.append(path)
    return paths


def _comic_page_caption_paragraphs(
    panel: Panel,
    plan_panel: PanelBalloonPlan | None,
    lettering_mode: str = DEFAULT_LETTERING_MODE,
) -> list[str]:
    from .balloons import caption_lines_for_mode

    lines = build_panel_overlay_text(panel, mode="card_form")
    return list(caption_lines_for_mode(lines, plan_panel, lettering_mode))


def validate_project_balloon_plan(project: str | Path) -> dict[str, Any]:
    """CLI entry: validate story/balloon_plan.json against approved panels and text."""
    root = Path(project)
    package = _artifact_package(root)
    return validate_balloon_plan(
        root,
        panel_dialogue=_panel_letterable_lines(package),
        expected_panel_count=len(package.storyboard),
    )


def _panel_letterable_lines(package: AdaptationPackage) -> dict[int, list[str]]:
    """All approved text lines a balloon may quote, per panel index."""
    lines: dict[int, list[str]] = {}
    for panel in package.storyboard:
        candidates = list(panel.dialogue)
        candidates.extend(build_panel_overlay_text(panel, mode="card_form"))
        candidates.extend(build_panel_overlay_text(panel, mode="long_form"))
        if panel.interior_monologue:
            candidates.append(panel.interior_monologue)
        lines[panel.index] = [item for item in candidates if item]
    return lines


def _comic_page_rects(template: str, count: int, width: int, height: int) -> list[tuple[int, int, int, int]]:
    margin = 72
    gap = 26
    top = 190
    bottom = height - 74
    usable_w = width - margin * 2
    usable_h = bottom - top
    if count <= 1 or template == "hero":
        return [(margin, top, width - margin, bottom)]
    if template == "two-vertical" or count == 2:
        h = (usable_h - gap) // 2
        return [(margin, top, width - margin, top + h), (margin, top + h + gap, width - margin, bottom)][:count]
    if template == "three-beat" or count == 3:
        hero_h = int(usable_h * 0.48)
        small_h = usable_h - hero_h - gap
        small_w = (usable_w - gap) // 2
        return [
            (margin, top, width - margin, top + hero_h),
            (margin, top + hero_h + gap, margin + small_w, bottom),
            (margin + small_w + gap, top + hero_h + gap, width - margin, bottom),
        ][:count]
    if template == "one-plus-two":
        hero_w = int(usable_w * 0.58)
        small_h = (usable_h - gap) // 2
        return [
            (margin, top, margin + hero_w, bottom),
            (margin + hero_w + gap, top, width - margin, top + small_h),
            (margin + hero_w + gap, top + small_h + gap, width - margin, bottom),
        ][:count]
    if template == "two-plus-one":
        hero_w = int(usable_w * 0.58)
        small_h = (usable_h - gap) // 2
        return [
            (margin, top, margin + usable_w - hero_w - gap, top + small_h),
            (margin, top + small_h + gap, margin + usable_w - hero_w - gap, bottom),
            (width - margin - hero_w, top, width - margin, bottom),
        ][:count]
    if template == "full-bleed-inset":
        hero = (margin, top, width - margin, bottom)
        inset_w = int(usable_w * 0.36)
        inset_h = int(usable_h * 0.32)
        rects = [hero, (width - margin - inset_w - 24, bottom - inset_h - 24, width - margin - 24, bottom - 24)]
        return rects[:count]
    rows = 2
    cols = 2
    cell_w = (usable_w - gap) // cols
    cell_h = (usable_h - gap) // rows
    rects = []
    for index in range(min(count, 4)):
        row, col = divmod(index, cols)
        x0 = margin + col * (cell_w + gap)
        y0 = top + row * (cell_h + gap)
        rects.append((x0, y0, x0 + cell_w, y0 + cell_h))
    return rects


def _draw_page_header(draw: ImageDraw.ImageDraw, page: dict[str, Any], package: AdaptationPackage, page_index: int, fonts: dict[str, ImageFont.FreeTypeFont], width: int) -> None:
    draw.text((72, 58), package.episode_title or package.book_title, font=fonts["small"], fill=(95, 86, 72))
    # page["purpose"] (setup/escalation/...) is a production beat label, not reader-facing copy.
    draw.text((72, 92), f"第 {page_index} 页", font=fonts["title"], fill=(54, 45, 33))
    draw.line((72, 150, width - 72, 150), fill=(184, 157, 108), width=2)


def _draw_comic_page_panel(
    page: Image.Image,
    draw: ImageDraw.ImageDraw,
    panel_path: Path,
    rect: tuple[int, int, int, int],
    paragraphs: list[str],
    fonts: dict[str, ImageFont.FreeTypeFont],
    style_id: str | None = None,
    plan_panel: PanelBalloonPlan | None = None,
    lettering_mode: str = DEFAULT_LETTERING_MODE,
) -> None:
    x0, y0, x1, y1 = rect
    draw.rectangle(rect, fill=(250, 247, 239), outline=(68, 55, 38), width=3)
    pad = 10
    caption_h = _caption_box_height(draw, paragraphs, x1 - x0 - pad * 2, fonts["body"])
    caption_h = min(max(caption_h, 98), max(98, int((y1 - y0) * 0.30)))
    art_rect = (x0 + pad, y0 + pad, x1 - pad, y1 - pad - caption_h)
    caption_rect = (x0 + pad, y1 - pad - caption_h + 8, x1 - pad, y1 - pad)
    art_size = (art_rect[2] - art_rect[0], art_rect[3] - art_rect[1])
    with Image.open(panel_path) as source:
        art = ImageOps.contain(source.convert("RGB"), art_size, method=Image.Resampling.LANCZOS)
        paste_x = art_rect[0] + (art_size[0] - art.width) // 2
        paste_y = art_rect[1] + (art_size[1] - art.height) // 2
        image_rect = (paste_x, paste_y, paste_x + art.width, paste_y + art.height)
        page.paste(art, (paste_x, paste_y))
    if plan_panel is not None:
        render_panel_overlays(page, image_rect, plan_panel, font_family="sans", ink=(32, 30, 27), viewport=(0.0, 0.0, 1.0, 1.0), lettering_mode=lettering_mode, profile=profile_for_style(style_id))
    draw.rectangle(caption_rect, fill=(245, 238, 220), outline=(198, 173, 126), width=1)
    _draw_caption_text(draw, paragraphs, caption_rect, fonts["body"])


def _cap_caption_paragraphs(paragraphs: list[str], limit: int = 3) -> list[str]:
    """Keep at most ``limit`` caption paragraphs WITHOUT dropping any text.

    Overflow is merged into the last kept paragraph instead of being silently
    sliced away (audit A9: comic-page caption used ``paragraphs[:3]`` and simply
    lost the 4th paragraph). Upstream text_budget already caps card_form at 3
    paragraphs; this is the render-layer guarantee that even if that gate is
    bypassed, sentences get compacted, never swallowed. The box height is
    computed from the SAME capped list so nothing overflows the drawn rect.
    """
    if len(paragraphs) <= limit:
        return list(paragraphs)
    kept = [p for p in paragraphs[: limit - 1]]
    tail = " ".join(p.strip() for p in paragraphs[limit - 1:] if p.strip())
    kept.append(tail)
    return kept


def _caption_box_height(draw: ImageDraw.ImageDraw, paragraphs: list[str], width: int, font: ImageFont.FreeTypeFont) -> int:
    if not paragraphs:
        return 84
    capped = _cap_caption_paragraphs(paragraphs)
    text_w = width - 30
    line_h = _font_line_height(draw, font)
    lines = 0
    for paragraph in capped:
        lines += max(1, len(_wrap_text(draw, paragraph, text_w, font)))
    return 30 + lines * (line_h + 4) + max(0, len(capped) - 1) * 8


def _draw_caption_text(draw: ImageDraw.ImageDraw, paragraphs: list[str], rect: tuple[int, int, int, int], font: ImageFont.FreeTypeFont) -> None:
    x0, y0, x1, y1 = rect
    x = x0 + 14
    y = y0 + 12
    max_w = x1 - x0 - 28
    for paragraph in _cap_caption_paragraphs(paragraphs):
        for line in _wrap_text(draw, paragraph, max_w, font):
            if y + _font_line_height(draw, font) > y1 - 8:
                return
            draw.text((x, y), line, font=font, fill=(50, 43, 34))
            y += _font_line_height(draw, font) + 4
        y += 8


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, max_width: int, font: ImageFont.FreeTypeFont) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        if draw.textlength(candidate, font=font) <= max_width or not current:
            current = candidate
            continue
        lines.append(current)
        current = char
    if current:
        lines.append(current)
    return lines


def _font_line_height(draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont) -> int:
    box = draw.textbbox((0, 0), "测试", font=font)
    return box[3] - box[1]


def _comic_page_fonts() -> dict[str, ImageFont.FreeTypeFont]:
    font_path = _find_cjk_font()
    return {
        "title": load_variant(font_path, 34, "bold"),
        "body": load_variant(font_path, 28, "regular"),
        "small": load_variant(font_path, 22, "regular"),
    }


def _find_cjk_font() -> Path:
    return find_cjk_font()


def _artifact_package(root: Path) -> AdaptationPackage:
    project = _read_json(root / "project.json")
    try:
        story = load_episode(root)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        story = {}
    panel_paths = sorted((root / "assets" / "panels").glob("*.png"), key=lambda path: path.name)
    panels: list[Panel] = []
    story_panels = flatten_episode_panels(story)
    for index, _ in enumerate(panel_paths, start=1):
        source = story_panels[index - 1] if index - 1 < len(story_panels) and isinstance(story_panels[index - 1], dict) else {}
        normalized = normalize_story_panel_for_package({**source, "index": index})
        panels.append(
            Panel(
                index=index,
                beat=str(normalized.get("beat") or f"Panel {index}"),
                visual=str(normalized.get("visual") or "Approved comic panel."),
                dialogue=tuple(str(item) for item in normalized.get("dialogue", ()) if item),
                narration=str(normalized.get("narration") or " "),
                comment_hook=str(normalized.get("comment_hook") or ""),
                scene_setting=str(normalized.get("scene_setting", "")),
                interior_monologue=str(normalized.get("interior_monologue", "")),
                connective_prose=str(normalized.get("connective_prose", "")),
                reality_mapping=str(normalized.get("reality_mapping", "")),
                card_copy=tuple(str(item) for item in normalized.get("card_copy", ())),
                long_copy=tuple(str(item) for item in normalized.get("long_copy", ())),
                invented_dialogue=tuple(str(item) for item in normalized.get("invented_dialogue", ())),
                visual_weight=str(source.get("visual_weight") or "normal"),
                layout_hint=str(source.get("layout_hint") or "normal"),
                beat_duration=str(source.get("beat_duration") or "normal"),
                visual_density=str(source.get("visual_density") or "medium"),
                text_density=str(source.get("text_density") or "medium"),
                reveal_priority=str(source.get("reveal_priority") or "normal"),
                pause_after=bool(source.get("pause_after", False)),
                emotional_anchor=bool(source.get("emotional_anchor", False)),
                anchor_subject=str(source.get("anchor_subject") or ""),
                anchor_note=str(source.get("anchor_note") or ""),
                hook_type=str(source.get("hook_type") or ""),
                hook_line=str(source.get("hook_line") or ""),
                is_cover_source=bool(source.get("is_cover_source", False)),
            )
        )
    title = str(story.get("book_title") or project.get("book_title") or project.get("project_title") or root.name)
    return AdaptationPackage(
        book_title=title,
        author=str(story.get("author") or ""),
        episode_title=str(story.get("episode_title") or f"《{title}》EP1"),
        suitability=Suitability(True, "artifact-materialized", "Approved assets were materialized into a comic package."),
        covered_points=tuple(story.get("covered_points", [])) if isinstance(story.get("covered_points", []), list) else (),
        core_ideas=(CoreIdea(title="本话主旨", kernel=str(story.get("primary_thesis") or " "), dramatization=" "),),
        methods=("artifact-materializer", "post-production-lettering"),
        light_shell="漫画阅读包",
        hard_core=str(story.get("primary_thesis") or " "),
        characters=(Character("角色", "approved", "approved character reference", "locked", "approved character"),),
        character_relationship="approved project cast",
        storyboard=tuple(panels),
        title_candidates=(str(story.get("episode_title") or title),),
        style_id=str(story.get("style_id") or "editorial"),
    )


# Canonical approved panels are exactly NN.png — anything else in
# assets/panels/ is not a shippable deliverable.
_PANEL_CANONICAL_RE = re.compile(r"\d{2}\.png")
# Exact final/ payload a public or private bundle may carry. Top-level names
# plus per-directory suffix allowlists; everything else is a hard error.
_BUNDLE_FINAL_TOP_FILES = {
    "comic-long.png",
    "comic.pdf",
    "comic.cbz",
    "comic.epub",
    "仅自用-PRIVATE-DO-NOT-SHARE.txt",
}
_BUNDLE_FINAL_DIRS = {
    "cards": {".png"},
    "cover": {".png", ".json"},
    "comic-pages": {".png"},
}


def _collect_bundle_allowlist(root: Path, output: Path) -> list[Path]:
    """Strict allowlist collection for public/private bundles; fail closed.

    Rejects symlinks/junctions, .REVOKED artifacts, unexpected files and
    escaped realpaths instead of silently包ing them (release audit v5.13.1
    P0-3 / P1-8).
    """
    files: list[Path] = []
    root_real = root.resolve()

    def _guard(path: Path) -> Path:
        if path.is_symlink():
            raise ValueError(f"refusing to bundle a symlink/junction: {path.relative_to(root).as_posix()}")
        real = path.resolve()
        if root_real not in real.parents and real != root_real:
            raise ValueError(f"refusing to bundle a path that escapes the project root: {path}")
        return path

    panels = root / "assets" / "panels"
    if panels.is_dir():
        for path in sorted(panels.iterdir()):
            if not path.is_file():
                continue
            if _PANEL_CANONICAL_RE.fullmatch(path.name):
                files.append(_guard(path))
            else:
                raise ValueError(
                    f"unexpected file in assets/panels/ (only NN.png canonical panels ship): {path.name}"
                )
    final = root / "final"
    if final.is_dir():
        for path in sorted(final.rglob("*")):
            if not path.is_file():
                continue
            if path.resolve() == output.resolve() or path.name in _BUNDLE_SIBLING_NAMES:
                continue
            if path.name.endswith(".REVOKED"):
                raise ValueError(
                    f"revoked artifact found in final/ — move it to quarantine/ before composing: {path.name}"
                )
            relative = path.relative_to(final)
            parts = relative.parts
            if len(parts) == 1:
                if parts[0] in _BUNDLE_FINAL_TOP_FILES:
                    files.append(_guard(path))
                    continue
            elif len(parts) == 2 and parts[0] in _BUNDLE_FINAL_DIRS:
                if path.suffix.lower() in _BUNDLE_FINAL_DIRS[parts[0]]:
                    files.append(_guard(path))
                    continue
            raise ValueError(
                "unexpected file in final/ is not on the bundle allowlist (remove it or re-run "
                f"compose in a clean final/): {relative.as_posix()}"
            )
    return files


def _write_artifact_production_zip(
    root: Path,
    output: Path,
    *,
    include_debug: bool = False,
    bundle_kind: str | None = None,
    rights_reasons: list[str] | None = None,
) -> Path:
    """Write the production bundle at its rights-decided tier.

    Public/private tiers carry finished deliverables only. The raw book text,
    planning scratch, prompts and review notes stay OUT — the old bundle leaked
    the full (possibly copyrighted) source and internal prompts to anyone the
    user shared production.zip with (2026-07 audit A10). The finished panels,
    captions and PDF/EPUB still CONTAIN adapted content and short source
    quotes by design — the bundle manifest says so instead of promising
    otherwise. include_debug=True (CLI --debug-bundle) adds the full working
    tree and is never a public artifact.
    """
    if include_debug:
        include_roots: tuple[str, ...] = ("project.json", "manifest.json", "state.json")
        include_dirs: tuple[str, ...] = (
            "source", "planning", "story", "prompts", "assets/references", "assets/panels", "review", "qa", "final",
        )
        files: list[Path] = []
        for name in include_roots:
            path = root / name
            if path.exists():
                files.append(path)
        for dirname in include_dirs:
            base = root / dirname
            if not base.exists():
                continue
            files.extend(
                path
                for path in base.rglob("*")
                if path.is_file() and path.resolve() != output.resolve() and path.name not in _BUNDLE_SIBLING_NAMES
            )
    else:
        # Public/private tiers use a STRICT allowlist instead of sweeping the
        # whole of final/ — the old recursive collect re-packed anything that
        # happened to live there, including revoked archives and stray files
        # (release audit v5.13.1 P0-3 / P1-8). Anything not on the list fails
        # closed rather than shipping silently.
        files = _collect_bundle_allowlist(root, output)
    stamp = root / "qa" / "delivery-gate.json"
    if not include_debug and stamp.exists():
        files.append(stamp)
    manifest = {
        "schema_version": MANIFEST_VERSION,
        "bundle": bundle_kind or ("debug" if include_debug else "public"),
        "paths_are_relative": True,
        "content_notice": (
            "Finished deliverables adapt the source work: panels, captions and exports may contain "
            "short source quotes and identifiable story content. Excluded from this bundle: raw source "
            "text, planning files and prompts (debug bundle only)."
        ),
        "rights_reasons": list(rights_reasons or []),
        "files": [_rel(root, path) for path in files],
    }
    # Two-phase commit: write to a temp name, verify the archive opens, then
    # atomically swap. A crash between stamp and archive used to leave a
    # project that claimed success with no production bundle at all (release
    # audit v5.13.2 P0-1).
    temp = output.with_name(output.name + ".tmp")
    with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("production-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        for path in files:
            archive.write(path, _rel(root, path))
    with zipfile.ZipFile(temp) as verify_archive:
        if verify_archive.testzip() is not None:
            temp.unlink(missing_ok=True)
            raise ValueError(f"production archive failed verification and was discarded: {output.name}")
    os.replace(temp, output)
    return output


def _generated_image_roots() -> list[Path]:
    roots: list[Path] = []
    env_dir = os.environ.get("BOOK_TO_COMIC_GENERATED_IMAGES_DIR")
    if env_dir:
        roots.append(Path(env_dir))
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        roots.append(Path(codex_home) / "generated_images")
    roots.append(Path.home() / ".codex" / "generated_images")
    deduped: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        resolved = root.expanduser().resolve()
        if resolved not in seen:
            seen.add(resolved)
            deduped.append(resolved)
    return deduped


def _iter_image_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES)


def _file_record(path: Path, root: Path) -> dict[str, object]:
    stat = path.stat()
    return {
        "root": str(root),
        "path": str(path),
        "relative_path": path.relative_to(root).as_posix(),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def _discover_single_new_image(snapshot_path: Path) -> Path:
    snapshot = _read_json(snapshot_path)
    before = {str(item["path"]): (item.get("size"), item.get("mtime_ns")) for item in snapshot.get("files", []) if isinstance(item, dict)}
    candidates: list[Path] = []
    for root_text in snapshot.get("roots", []):
        root = Path(str(root_text))
        for path in _iter_image_files(root):
            stat = path.stat()
            marker = (stat.st_size, stat.st_mtime_ns)
            if str(path) not in before or before[str(path)] != marker:
                candidates.append(path)
    if len(candidates) != 1:
        names = ", ".join(path.name for path in candidates) or "none"
        raise ValueError(f"Expected exactly one new image after snapshot; found {len(candidates)}: {names}")
    return candidates[0]


def _wait_for_stable_file(path: Path, attempts: int = 10, delay: float = 0.1) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"Image source does not exist: {path}")
    previous = (-1, -1)
    for _ in range(attempts):
        stat = path.stat()
        current = (stat.st_size, stat.st_mtime_ns)
        if current == previous and stat.st_size > 0:
            return path
        previous = current
        time.sleep(delay)
    raise ValueError(
        f"Image file did not stabilize after {attempts} checks (still being written?); "
        f"retry once the generator finishes: {path}"
    )


def _normalize_png(source: Path, output: Path, min_short_side: int) -> tuple[int, int]:
    if source.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
        raise ValueError(f"Unsupported image format: {source.suffix}")
    # Content-based admission: extension checks alone let renamed PSD/FITS
    # payloads reach the vulnerable decoders (release audit v5.13.1 P1-6).
    from .image_safety import open_image_checked

    open_image_checked(source, purpose="candidate image")
    with Image.open(source) as image:
        normalized = ImageOps.exif_transpose(image).convert("RGB")
        width, height = normalized.size
        if min(width, height) < min_short_side:
            raise ValueError(f"Image short side is too small: {width}x{height} < {min_short_side}")
        normalized.save(output, "PNG", optimize=True)
    return width, height


def _upsert_asset(root: Path, item: dict[str, object]) -> None:
    manifest = _manifest(root)
    manifest["assets"] = [
        existing
        for existing in manifest.get("assets", [])
        if not (existing.get("asset_id") == item["asset_id"] and existing.get("version") == item["version"])
    ]
    manifest["assets"].append(item)
    _write_manifest(root, manifest)


def _latest_asset(manifest: dict[str, Any], asset_id: str) -> dict[str, Any]:
    matches = [item for item in manifest.get("assets", []) if item.get("asset_id") == asset_id]
    if not matches:
        raise ValueError(f"Asset not found: {asset_id}")
    return sorted(matches, key=lambda item: int(item.get("version", 0)))[-1]


def _manifest(root: Path) -> dict[str, Any]:
    _require_project(root)
    path = root / "manifest.json"
    if not path.exists():
        raise FileNotFoundError(f"manifest.json is missing: {path}")
    data = _read_json(path)
    data.setdefault("assets", [])
    return data


def _write_manifest(root: Path, data: dict[str, Any]) -> None:
    data["updated_at"] = _now()
    _write_json(root / "manifest.json", data)


def _write_state(root: Path, status: str, manifest: dict[str, Any] | None = None, **extra: object) -> None:
    if manifest is None:
        manifest_path = root / "manifest.json"
        manifest = _read_json(manifest_path) if manifest_path.exists() else {"assets": []}
    approved_assets = [item for item in manifest.get("assets", []) if isinstance(item, dict) and item.get("status") == "approved"]
    approved_panels = sorted(
        int(item["panel_index"])
        for item in approved_assets
        if item.get("kind") == "panel" and item.get("panel_index") is not None
    )
    state: dict[str, object] = {
        "schema_version": MANIFEST_VERSION,
        "status": status,
        "updated_at": _now(),
        "approved_assets": len(approved_assets),
        "approved_panel_count": len(approved_panels),
        "approved_panels": approved_panels,
        "character_reference_approved": any(item.get("kind") == "character-reference" for item in approved_assets),
    }
    state.update(extra)
    _write_json(root / "state.json", state)


def _require_project(root: Path) -> None:
    if not root.exists():
        raise FileNotFoundError(f"Project directory does not exist: {root}")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rel(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _slug(text: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "-" for char in text).strip("-")
    return "-".join(part for part in slug.split("-") if part) or "book-to-comic"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
