"""User-specified free-form custom art style.

Stored on ``planning/visual_identity.json`` as ``custom_art_style`` and injected
at the very top of every image prompt by ``prompt_compiler`` (highest priority
over the 9 built-in style_id looks). It lets a user render the comic in ANY look
— e.g. ``中国水墨留白``, ``水彩绘本``, ``美式复古印刷`` — with no API key, for both
Codex auto-generation and the manual image inbox.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_FLAT_STYLES_PATH = Path(__file__).resolve().parent / "presets" / "flat_styles.json"
_FLAT_CACHE: dict[str, Any] | None = None


def _visual_identity_path(root: Path) -> Path:
    return root / "planning" / "visual_identity.json"


def load_flat_styles() -> dict[str, Any]:
    """The self-contained flat style library (id -> {prompt, balloon_placement, ...})."""
    global _FLAT_CACHE
    if _FLAT_CACHE is None:
        data = json.loads(_FLAT_STYLES_PATH.read_text(encoding="utf-8"))
        _FLAT_CACHE = data.get("styles", {}) if isinstance(data, dict) else {}
    return _FLAT_CACHE


def flat_style_ids() -> list[str]:
    return sorted(load_flat_styles().keys())


def get_flat_style(style_id: str) -> dict[str, Any] | None:
    entry = load_flat_styles().get(style_id)
    return entry if isinstance(entry, dict) else None


def flat_style_balloon_placement(project_dir: str | Path) -> str | None:
    """Balloon placement recorded when a flat style was applied (in_art / caption)."""
    root = Path(project_dir)
    for cand in (root / "project.json", root / "comic" / "project.json"):
        if cand.exists():
            try:
                data = json.loads(cand.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            value = data.get("flat_style_balloon_placement")
            if value in ("in_art", "caption"):
                return value
    return None


def set_flat_style(project_dir: str | Path, style_id: str) -> dict[str, Any]:
    """Apply a library flat style: write its full prompt into custom_art_style,
    and record its balloon placement on project.json so compose can honor it."""
    entry = get_flat_style(style_id)
    if entry is None:
        raise ValueError(f"Unknown flat style '{style_id}'. Known: {', '.join(flat_style_ids())}")
    result = set_custom_art_style(project_dir, str(entry.get("prompt") or ""))
    avoid = str(entry.get("avoid") or "").strip()
    if avoid:
        root = Path(project_dir)
        vi_path = _visual_identity_path(root)
        data = json.loads(vi_path.read_text(encoding="utf-8"))
        data["custom_art_style_avoid"] = avoid
        vi_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    placement = entry.get("balloon_placement")
    if placement in ("in_art", "caption"):
        root = Path(project_dir)
        for cand in (root / "project.json", root / "comic" / "project.json"):
            if cand.exists():
                data = json.loads(cand.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    data["flat_style_balloon_placement"] = placement
                    cand.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                break
    result["flat_style"] = style_id
    result["balloon_placement"] = placement
    return result


def set_custom_art_style(project_dir: str | Path, style_text: str, *, licensed_name: bool = False) -> dict[str, Any]:
    root = Path(project_dir)
    vi_path = _visual_identity_path(root)
    if not vi_path.exists():
        raise FileNotFoundError(
            f"planning/visual_identity.json not found at {vi_path}. "
            "Plan the project first (so its visual identity exists), then set the art style."
        )
    data = json.loads(vi_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("visual_identity.json is not a JSON object.")
    text = " ".join(str(style_text).split())
    if not text:
        raise ValueError("Custom art style text cannot be empty.")
    data["custom_art_style"] = text
    # Recorded basis, not detection: code cannot enumerate living artists, so
    # the enforceable layer is (a) this declaration and (b) the no-copying
    # clause the prompt compiler ALWAYS appends (release audit P1-10).
    data["custom_art_style_basis"] = "licensed-name" if licensed_name else "technique"
    vi_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"project": str(root), "custom_art_style": text, "basis": data["custom_art_style_basis"]}


def get_custom_art_style(project_dir: str | Path) -> str:
    root = Path(project_dir)
    vi_path = _visual_identity_path(root)
    if not vi_path.exists():
        return ""
    try:
        data = json.loads(vi_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("custom_art_style", "")).strip()


def set_card_theme(project_dir: str | Path, theme: str) -> dict[str, Any]:
    """Record the carousel-card background theme in project.json.

    Formal compose refuses to run without one of the three themes — the field
    used to be advisory and a planning pass that skipped it silently shipped
    default white cards (v5.13.4). One value per project, uniform across the
    episode.
    """
    from .composer import CARD_THEMES

    value = str(theme or "").strip().lower()
    if value not in CARD_THEMES:
        raise ValueError(f"Unknown card theme '{theme}'. Pick one of: {', '.join(CARD_THEMES)}.")
    root = Path(project_dir)
    project_file = root / "project.json"
    if not project_file.exists():
        raise FileNotFoundError(f"project.json not found at {project_file}. init the project first.")
    data = json.loads(project_file.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"project.json must contain a JSON object: {project_file}")
    data["card_theme"] = value
    project_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"project": str(root), "card_theme": value}
