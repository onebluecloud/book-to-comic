from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from .composer import render_cover_overlay
from .project_layout import load_episode
from .story_gate import flatten_episode_panels


def build_cover_assets(project: str | Path) -> dict[str, Any]:
    root = Path(project)
    episode = load_episode(root)
    panels = flatten_episode_panels(episode)
    source_index, source_panel = _cover_source_panel(panels)
    base_panel = root / "assets" / "panels" / f"{source_index:02d}.png"
    if not base_panel.exists():
        raise FileNotFoundError(f"Cover base panel is missing: {base_panel}")

    output_dir = root / "final" / "cover"
    output_dir.mkdir(parents=True, exist_ok=True)
    title = str(episode.get("book_title") or _read_project_title(root))
    # Reader-facing subtitle: the episode title. Never pipeline slogans
    # ("书籍 -> 漫画" shipped on real covers before this).
    subtitle = str(episode.get("episode_title") or "").strip()
    if subtitle == title:
        subtitle = ""
    hooks = _cover_hooks(episode, source_panel)
    candidates = []
    for index, hook in enumerate(hooks[:3], start=1):
        layout = "big-title-on-panel" if index == 1 else "input-to-output" if index == 2 else "editorial-hook"
        palette = "editorial-dark" if index != 3 else "editorial-warm"
        path = output_dir / f"cover-{index:02d}.png"
        render_cover_overlay(
            base_panel,
            path,
            title=title,
            hook_line=hook,
            subtitle=subtitle,
            layout=layout,
            palette=palette,
        )
        candidates.append(
            {
                "file": path.relative_to(root).as_posix(),
                "hook_line": hook,
                "layout": layout,
                "base_panel": f"{source_index:02d}.png",
                "palette": palette,
            }
        )
    manifest = {
        "schema_version": "1.0",
        "updated_at": _now(),
        "source": "post-production Pillow overlay; image model did not render readable text",
        "candidates": candidates,
    }
    _write_json(output_dir / "cover-manifest.json", manifest)
    return manifest


def _cover_source_panel(panels: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    for index, panel in enumerate(panels, start=1):
        if isinstance(panel, dict) and panel.get("is_cover_source") is True:
            return index, panel
    if not panels:
        raise ValueError("Cannot build cover without episode panels.")
    return 1, panels[0]


def _cover_hooks(episode: dict[str, Any], panel: dict[str, Any]) -> list[str]:
    hooks: list[str] = []
    for value in (
        panel.get("hook_line"),
        episode.get("adaptation_strategy", {}).get("novelty_hook") if isinstance(episode.get("adaptation_strategy"), dict) else "",
        f"我把《{episode.get('book_title', '这本书')}》画成第一话",
    ):
        text = str(value or "").strip()
        if text and text not in hooks:
            hooks.append(text)
    while len(hooks) < 3:
        hooks.append("这本书，原来可以这样读")
    return hooks


def _read_project_title(root: Path) -> str:
    path = root / "project.json"
    if not path.exists():
        return root.name
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return root.name
    return str(data.get("project_title") or data.get("book_title") or root.name)


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
