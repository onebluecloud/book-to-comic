"""Series ledger: one episode = one project directory, honestly.

v5.12 promised "后续话用 --episode N 推进" while every command silently read
``story/episode-001.json`` — an "EP02" run relabeled EP01 content and
overwrote its prompts (2026-07 audit P0-3). Instead of threading a second
episode through every module (materializer, prompts, assets, QA, final — a
rewrite of the whole invariant "one project, one episode"), the series layer
keeps that invariant and makes it explicit:

* ``series.json`` is the book-level ledger: the beat-account plan of episodes
  and where each episode's project lives;
* ``add-episode`` scaffolds the next episode as its OWN project directory and
  copies the series-level planning bibles (characters, environments, style,
  visual identity, grounding) from the previous episode so visual continuity
  carries over;
* per-episode gates/assets/QA/final isolation is free — separate directories
  cannot overwrite each other.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .project_layout import validate_episode_id

SERIES_FILE = "series.json"
SERIES_SCHEMA_VERSION = "1.0"
# Planning files that define the series look & rights homework; copied forward
# so every episode starts from the same bible instead of re-inventing faces.
SERIES_BIBLE_FILES = (
    "planning/series_bible.json",
    "planning/character_bible.json",
    "planning/environment_bible.json",
    "planning/style_bible.json",
    "planning/visual_identity.json",
    "planning/grounding_profile.json",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def series_path(series_dir: str | Path) -> Path:
    return Path(series_dir) / SERIES_FILE


def load_series(series_dir: str | Path) -> dict[str, Any]:
    path = series_path(series_dir)
    if not path.is_file():
        raise FileNotFoundError(f"Series ledger not found: {path}. Run init-series first.")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("episodes"), list):
        raise ValueError(f"Series ledger is not a valid series object: {path}")
    return data


def _write_series(series_dir: Path, data: dict[str, Any]) -> Path:
    path = series_path(series_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _now()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def init_series(
    series_dir: str | Path,
    *,
    book: str,
    episodes: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Create the series ledger. ``episodes`` is the beat-account plan:
    [{"episode_id": "EP01", "title": "..."}, ...]. EP01 is added if absent."""
    root = Path(series_dir)
    path = series_path(root)
    if path.exists():
        raise FileExistsError(f"Series ledger already exists: {path} (edit it, don't re-init).")
    planned = list(episodes or [])
    if not any(str(item.get("episode_id")) == "EP01" for item in planned):
        planned.insert(0, {"episode_id": "EP01", "title": ""})
    entries = []
    seen: set[str] = set()
    for item in planned:
        episode_id = validate_episode_id(str(item.get("episode_id") or ""))
        if episode_id in seen:
            raise ValueError(f"Duplicate episode_id in plan: {episode_id}")
        seen.add(episode_id)
        entries.append(
            {
                "episode_id": episode_id,
                "title": str(item.get("title") or "").strip(),
                "status": "planned",
                "project_dir": "",
            }
        )
    data = {
        "schema_version": SERIES_SCHEMA_VERSION,
        "book_title": book,
        "created_at": _now(),
        "episodes": entries,
    }
    _write_series(root, data)
    return data


def ingest_source(
    target_dir: str | Path,
    source_file: str | Path,
    *,
    into: str = "series",
) -> dict[str, Any]:
    """Non-destructively import the book text into a series root or an
    EXISTING project.

    Before this command the two documented flows both dead-ended (release
    audit v5.13.1 P0-4): ``extract`` refuses to run inside an existing
    project, and text extracted at the series root never reached EP01. This
    is the missing legal write path: it ONLY writes ``source/raw_text.txt``
    plus an ingest manifest — it never touches project.json, manifest,
    story or planning, and it refuses to overwrite existing source text
    (there is deliberately no --force; replacing the book text of a live
    project must be a manual, visible act).
    """
    from .project_workflow import _extract_text

    target = Path(target_dir)
    src = Path(source_file)
    if not src.is_file():
        raise FileNotFoundError(f"Book file does not exist: {src}")
    if into == "series":
        load_series(target)  # must already be a series root (init-series first)
    elif into == "project":
        if not (target / "project.json").is_file():
            raise FileNotFoundError(
                f"{target} is not a project (no project.json). Run init-project first, "
                "or use --series to ingest at the series root."
            )
    else:
        raise ValueError("into must be 'series' or 'project'")

    destination = target / "source" / "raw_text.txt"
    if destination.exists():
        raise FileExistsError(
            f"{destination} already exists. ingest-source never overwrites book text; "
            "delete the file manually first if you truly mean to replace it."
        )
    text = _extract_text(src)
    if not text.strip():
        raise ValueError(f"No text could be extracted from {src}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")
    record = {
        "schema_version": "1.0",
        "ingested_at": _now(),
        "original_name": src.name,
        "original_sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "text_chars": len(text),
        "ingested_into": into,
    }
    (target / "source" / "ingest-manifest.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return record


def add_episode_project(
    series_dir: str | Path,
    *,
    episode_id: str,
    project_dir: str | Path | None = None,
    copy_bibles_from: str | Path | None = None,
    delivery_intent: str = "hardcore_showcase",
) -> dict[str, Any]:
    """Scaffold the next episode as its own project and register it.

    Bibles are copied from ``copy_bibles_from`` (default: the most recent
    episode with a registered project) so the cast keeps its faces. The new
    project then goes through the FULL official pipeline like any other —
    the series layer grants no gate shortcuts.
    """
    from .artifact_materializer import init_project

    root = Path(series_dir)
    data = load_series(root)
    episode_id = validate_episode_id(episode_id)
    entry = next((item for item in data["episodes"] if item.get("episode_id") == episode_id), None)
    if entry is None:
        entry = {"episode_id": episode_id, "title": "", "status": "planned", "project_dir": ""}
        data["episodes"].append(entry)
    if entry.get("project_dir"):
        existing = root / str(entry["project_dir"])
        raise FileExistsError(
            f"Episode {episode_id} already has a project at {existing}. "
            "Work there, or remove the ledger entry deliberately first."
        )

    source_project: Path | None = None
    if copy_bibles_from is not None:
        source_project = Path(copy_bibles_from)
        if not source_project.is_dir():
            raise FileNotFoundError(f"copy_bibles_from project does not exist: {source_project}")
    else:
        for item in reversed(data["episodes"]):
            registered = str(item.get("project_dir") or "")
            if registered and item.get("episode_id") != episode_id:
                candidate = (root / registered).resolve()
                if candidate.is_dir():
                    source_project = candidate
                    break

    target = Path(project_dir) if project_dir is not None else root / episode_id
    init_project(str(data.get("book_title") or "book"), target, delivery_intent=delivery_intent, episode_id=episode_id)

    copied: list[str] = []
    carried_card_theme = ""
    if source_project is not None:
        for relative in SERIES_BIBLE_FILES:
            source_file = source_project / relative
            if source_file.is_file():
                destination = target / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_file, destination)
                copied.append(relative)
        # Taste settings carry across the season: bibles above already carry
        # the art style; card_theme lives in project.json and is REQUIRED at
        # formal compose, so the new episode inherits the previous episode's
        # choice instead of drifting or failing on a missing field (v5.13.4).
        try:
            carried_card_theme = str(
                json.loads((source_project / "project.json").read_text(encoding="utf-8")).get("card_theme") or ""
            ).strip()
        except (OSError, json.JSONDecodeError, AttributeError):
            carried_card_theme = ""
        if carried_card_theme:
            project_file = target / "project.json"
            project_data = json.loads(project_file.read_text(encoding="utf-8"))
            project_data["card_theme"] = carried_card_theme
            project_file.write_text(json.dumps(project_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Hand the series-level book text over to the episode project — extracted
    # source used to strand at the series root while EP01's source-chunk
    # failed on a missing source/raw_text.txt (release audit v5.13.1 P0-4).
    source_handoff = ""
    series_source = root / "source" / "raw_text.txt"
    episode_source = target / "source" / "raw_text.txt"
    if series_source.is_file() and not episode_source.exists():
        episode_source.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(series_source, episode_source)
        source_handoff = hashlib.sha256(episode_source.read_bytes()).hexdigest()
        handoff_record = {
            "schema_version": "1.0",
            "ingested_at": _now(),
            "original_name": "raw_text.txt",
            "original_sha256": source_handoff,
            "text_sha256": source_handoff,
            "text_chars": len(episode_source.read_text(encoding="utf-8")),
            "ingested_into": "project",
            "handoff_from": "series source/raw_text.txt",
        }
        (target / "source" / "ingest-manifest.json").write_text(
            json.dumps(handoff_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    entry["status"] = "in_progress"
    try:
        entry["project_dir"] = str(Path(target).resolve().relative_to(root.resolve()))
    except ValueError:
        entry["project_dir"] = str(Path(target).resolve())
    _write_series(root, data)
    return {
        "episode_id": episode_id,
        "project_dir": str(target),
        "copied_bibles": copied,
        "copied_from": str(source_project) if source_project else "",
        "card_theme": carried_card_theme,
        "source_handoff_sha256": source_handoff,
        "note": (
            "Planning bibles carried over; this episode still walks the FULL official pipeline "
            "(planning gates, review records, image QA, compose) in its own directory."
        ),
    }


def series_status(series_dir: str | Path) -> dict[str, Any]:
    """Report each episode's real state, derived from its project on disk.

    Runs the FULL delivery validation per episode instead of trusting the
    stamp's passed flag — a project whose finals were deleted or tampered
    with used to report composed (release audit P0-2).
    """
    from .delivery_gate import load_delivery_stamp, validate_delivery

    root = Path(series_dir)
    data = load_series(root)
    episodes: list[dict[str, Any]] = []
    for item in data["episodes"]:
        entry = dict(item)
        registered = str(item.get("project_dir") or "")
        derived = "planned"
        if registered:
            project = root / registered if not Path(registered).is_absolute() else Path(registered)
            if not project.is_dir():
                derived = "missing"
            elif not ((project / "project.json").is_file() and (project / "story").is_dir()):
                # A directory missing its project markers is broken, not
                # composed — deleting project.json used to flip an episode to
                # "composed" via the not-applicable path (release audit
                # v5.13.2 P0-3).
                derived = "invalid-project"
            else:
                report = validate_delivery(project, raise_on_fail=False, write_report=False)
                if not report["has_final"] and load_delivery_stamp(project) is None:
                    derived = "in_progress"
                elif not report.get("applicable", True):
                    derived = "invalid-project"
                elif report["passed"]:
                    derived = "composed"
                else:
                    derived = "delivery-invalid"
                    entry["delivery_issues"] = report["issues"]
        entry["derived_status"] = derived
        episodes.append(entry)
    return {
        "schema_version": SERIES_SCHEMA_VERSION,
        "book_title": data.get("book_title"),
        "episodes": episodes,
    }
