from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from pathlib import Path
from typing import Any

from .project_layout import load_episode, save_episode
from .story_gate import ALLOWED_PANEL_ROLES, flatten_episode_panels
from .text_bible import panel_card_form_lines, panel_long_form_lines, panel_text_metrics


MANIFEST_VERSION = "2.0"
DEFAULT_MAX_CHARS = 1400
CARD_TEXT_BUDGET_BY_SHOT = {
    "establishing": 88,
    "wide": 84,
    "medium": 80,
    "close-up": 72,
    "insert": 60,
    "over-shoulder": 76,
    "insert/over-shoulder": 68,
}
LONG_FORM_BUDGET_BY_SHOT = {
    "establishing": 170,
    "wide": 160,
    "medium": 150,
    "close-up": 140,
    "insert": 115,
    "over-shoulder": 145,
    "insert/over-shoulder": 125,
}
BALLOON_BUDGET_BY_SHOT = CARD_TEXT_BUDGET_BY_SHOT


def source_chunk_project(
    project: str | Path,
    *,
    input_path: str | Path | None = None,
    chapter_id: str = "CH1",
    max_chars: int = DEFAULT_MAX_CHARS,
) -> dict[str, Any]:
    root = Path(project)
    source_path = Path(input_path) if input_path else root / "source" / "raw_text.txt"
    if not source_path.exists():
        raise FileNotFoundError(f"Source text is missing: {source_path}")
    text = source_path.read_text(encoding="utf-8")
    chunks = split_source_text(text, chapter_id=chapter_id, max_chars=max_chars)
    payload = {
        "schema_version": MANIFEST_VERSION,
        "created_at": _now(),
        "source_path": _project_relative(root, source_path),
        "chapter_id": chapter_id,
        "max_chars": max_chars,
        "chunks": chunks,
    }
    _write_json(root / "source" / "source_chunks.json", payload)
    return payload


def split_source_text(text: str, *, chapter_id: str = "CH1", max_chars: int = DEFAULT_MAX_CHARS) -> list[dict[str, Any]]:
    if max_chars <= 0:
        raise ValueError("max_chars must be positive.")
    paragraphs = [item.strip() for item in re.split(r"\n\s*\n+", text) if item.strip()]
    chunks: list[dict[str, Any]] = []
    buffer: list[str] = []
    start = 1
    chunk_index = 1
    for paragraph_index, paragraph in enumerate(paragraphs, start=1):
        next_text = "\n\n".join([*buffer, paragraph]) if buffer else paragraph
        if buffer and len(next_text) > max_chars:
            chunks.append(_source_chunk(chapter_id, chunk_index, start, paragraph_index - 1, buffer))
            chunk_index += 1
            buffer = [paragraph]
            start = paragraph_index
        else:
            if not buffer:
                start = paragraph_index
            buffer.append(paragraph)
    if buffer:
        chunks.append(_source_chunk(chapter_id, chunk_index, start, len(paragraphs), buffer))
    return chunks


def build_story_ir(project: str | Path) -> dict[str, Any]:
    root = Path(project)
    chunks_payload = _read_json(root / "source" / "source_chunks.json")
    episode_path = root / "story" / "episode-001.json"
    episode = load_episode(root)
    chunks = _episode_source_chunks(chunks_payload)
    if not chunks:
        raise ValueError("source/source_chunks.json has no chunks.")
    chunk_ids = {chunk["chunk_id"] for chunk in chunks}

    scenes = episode.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("story/episode-001.json must contain scenes[] before build-story-ir.")

    errors: list[str] = []
    scene_beats: list[dict[str, Any]] = []
    panel_scripts: list[dict[str, Any]] = []
    reading_order = 1
    for scene_index, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue
        beat_id = f"B{scene_index + 1:02d}"
        scene_id = _nonempty(scene.get("scene_id")) or f"S{scene_index + 1:02d}"
        source_refs = _string_list(scene.get("source_refs"))
        if not source_refs:
            errors.append(f"{scene_id}.source_refs is required; story_ir no longer guesses by scene index.")
        else:
            unknown = sorted(set(source_refs) - chunk_ids)
            if unknown:
                errors.append(f"{scene_id}.source_refs contains unknown chunk ids: {unknown}.")
        scene_beats.append(
            {
                "beat_id": beat_id,
                "scene_id": scene_id,
                "goal": _nonempty(scene.get("character_goal")) or _nonempty(scene.get("event")),
                "obstacle": _nonempty(scene.get("obstacle")),
                "turn": _nonempty(scene.get("turn")) or _nonempty(scene.get("callback_to_spine_event")),
                "visual_hook": _nonempty(scene.get("event")) or _nonempty(scene.get("story_function")),
                "source_refs": source_refs,
            }
        )
        panels = scene.get("panels")
        if not isinstance(panels, list):
            continue
        for panel_index, panel in enumerate(panels):
            if not isinstance(panel, dict):
                continue
            panel_id = _nonempty(panel.get("panel_id")) or f"P{reading_order:02d}"
            panel_refs = _string_list(panel.get("source_refs"))
            role = _nonempty(panel.get("panel_role"))
            action_verb = _nonempty(panel.get("action_verb"))
            if not panel_refs:
                errors.append(f"{panel_id}.source_refs is required; story_ir no longer copies scene refs into panels.")
            else:
                unknown = sorted(set(panel_refs) - chunk_ids)
                if unknown:
                    errors.append(f"{panel_id}.source_refs contains unknown chunk ids: {unknown}.")
            if role not in ALLOWED_PANEL_ROLES:
                errors.append(f"{panel_id}.panel_role is required and must be one of {sorted(ALLOWED_PANEL_ROLES)}.")
            if not action_verb:
                errors.append(f"{panel_id}.action_verb is required; story_ir no longer extracts verbs from action text.")
            panel["source_refs"] = panel_refs
            panel["panel_role"] = role
            panel["action_verb"] = action_verb
            panel["reading_order"] = reading_order
            _default_text_scaffold(panel, scene, role)
            panel["text_budgets"] = _text_budgets(panel)
            panel["text_metrics"] = panel_text_metrics(panel)
            panel["balloon_budget"] = panel["text_budgets"]["card_form"]
            panel_scripts.append(
                {
                    "panel_id": panel_id,
                    "beat_id": beat_id,
                    "panel_role": role,
                    "action_verb": action_verb,
                    "source_refs": panel_refs,
                    "copy_jobs": panel["copy_jobs"],
                    "text_budgets": panel["text_budgets"],
                }
            )
            reading_order += 1

    if errors:
        raise ValueError("; ".join(errors))

    referenced = {
        ref
        for item in [*scene_beats, *panel_scripts]
        for ref in _string_list(item.get("source_refs"))
    }
    episode["source_refs"] = sorted(referenced)
    episode["story_ir"] = {
        "source_chunks": chunks,
        "scene_beats": scene_beats,
        "panel_scripts": panel_scripts,
    }
    save_episode(root, episode)
    report = validate_source_coverage(root, write_report=True, raise_on_fail=False)
    return {
        "schema_version": MANIFEST_VERSION,
        "episode_path": _project_relative(root, episode_path),
        "source_chunk_count": len(chunks),
        "scene_beat_count": len(scene_beats),
        "panel_script_count": len(panel_scripts),
        "coverage": report["metrics"],
    }


def validate_source_coverage(
    project: str | Path,
    *,
    min_source_coverage: float = 0.9,
    max_balloon_overflow_rate: float = 0.01,
    write_report: bool = True,
    raise_on_fail: bool = True,
) -> dict[str, Any]:
    root = Path(project)
    episode = load_episode(root)
    panels = flatten_episode_panels(episode)
    source_ids = _story_ir_source_ids(episode)
    has_story_ir_source_chunks = bool(source_ids)
    missing_source_refs: list[str] = []
    unknown_source_refs: dict[str, list[str]] = {}
    missing_drawable_contract: list[str] = []
    balloon_overflow: list[str] = []
    reading_orders: list[int] = []
    panels_with_source = 0
    panels_drawable = 0

    for index, panel in enumerate(panels, start=1):
        panel_id = _nonempty(panel.get("panel_id")) or f"P{index:02d}"
        refs = _string_list(panel.get("source_refs"))
        unknown = sorted(set(refs) - source_ids) if source_ids else []
        if refs and has_story_ir_source_chunks and not unknown:
            panels_with_source += 1
        else:
            missing_source_refs.append(panel_id)
            if unknown:
                unknown_source_refs[panel_id] = unknown

        order = panel.get("reading_order")
        if isinstance(order, int):
            reading_orders.append(order)
        drawable_missing = _drawable_missing(panel)
        if drawable_missing:
            missing_drawable_contract.append(panel_id)
        else:
            panels_drawable += 1
        if _is_balloon_overflow(panel.get("balloon_budget")):
            balloon_overflow.append(panel_id)

    panel_count = len(panels)
    source_coverage = panels_with_source / panel_count if panel_count else 0.0
    drawable_panel_rate = panels_drawable / panel_count if panel_count else 0.0
    balloon_overflow_rate = len(balloon_overflow) / panel_count if panel_count else 0.0
    reading_order_passed = panel_count > 0 and sorted(reading_orders) == list(range(1, panel_count + 1))
    passed = (
        has_story_ir_source_chunks
        and source_coverage >= min_source_coverage
        and drawable_panel_rate == 1.0
        and balloon_overflow_rate <= max_balloon_overflow_rate
        and reading_order_passed
    )
    report = {
        "schema_version": MANIFEST_VERSION,
        "updated_at": _now(),
        "passed": passed,
        "has_story_ir_source_chunks": has_story_ir_source_chunks,
        "thresholds": {
            "min_source_coverage": min_source_coverage,
            "max_balloon_overflow_rate": max_balloon_overflow_rate,
            "required_drawable_panel_rate": 1.0,
        },
        "metrics": {
            "panel_count": panel_count,
            "source_coverage": round(source_coverage, 4),
            "drawable_panel_rate": round(drawable_panel_rate, 4),
            "balloon_overflow_rate": round(balloon_overflow_rate, 4),
            "reading_order_passed": reading_order_passed,
        },
        "missing_source_refs": missing_source_refs,
        "unknown_source_refs": unknown_source_refs,
        "missing_drawable_contract": missing_drawable_contract,
        "balloon_overflow_panels": balloon_overflow,
    }
    if write_report:
        _write_json(root / "qa" / "source-coverage-report.json", report)
    if raise_on_fail and not passed:
        raise ValueError("Source coverage validation failed.")
    return report


def _source_chunk(chapter_id: str, chunk_index: int, start: int, end: int, paragraphs: list[str]) -> dict[str, Any]:
    text = "\n\n".join(paragraphs)
    return {
        "chunk_id": f"{chapter_id}-{chunk_index:03d}",
        "chapter_id": chapter_id,
        "paragraph_start": start,
        "paragraph_end": end,
        "text_excerpt": _excerpt(text),
        "text": text,
        "char_count": len(text),
    }


def _episode_source_chunks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    chunks = payload.get("chunks", [])
    result: list[dict[str, Any]] = []
    if not isinstance(chunks, list):
        return result
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        result.append(
            {
                "chunk_id": _nonempty(chunk.get("chunk_id")),
                "chapter_id": _nonempty(chunk.get("chapter_id")),
                "paragraph_start": _int_or_zero(chunk.get("paragraph_start")),
                "paragraph_end": _int_or_zero(chunk.get("paragraph_end")),
                "text_excerpt": _nonempty(chunk.get("text_excerpt")) or _excerpt(_nonempty(chunk.get("text"))),
            }
        )
    return [chunk for chunk in result if chunk["chunk_id"] and chunk["chapter_id"] and chunk["text_excerpt"]]


def _story_ir_source_ids(episode: dict[str, Any]) -> set[str]:
    story_ir = episode.get("story_ir")
    if not isinstance(story_ir, dict):
        return set()
    chunks = story_ir.get("source_chunks")
    if not isinstance(chunks, list):
        return set()
    return {_nonempty(chunk.get("chunk_id")) for chunk in chunks if isinstance(chunk, dict) and _nonempty(chunk.get("chunk_id"))}


def _default_text_scaffold(panel: dict[str, Any], scene: dict[str, Any], role: str) -> None:
    layers = panel.get("text_layers")
    if not isinstance(layers, dict):
        layers = {}
    dialogue = _string_list(panel.get("dialogue")) or _string_list(layers.get("dialogue"))
    if dialogue:
        layers["dialogue"] = dialogue
    if not _nonempty(panel.get("scene_setting")) and not _string_list(layers.get("scene_setting")):
        scene_text = _nonempty(panel.get("life_scene")) or _nonempty(scene.get("event")) or _nonempty(panel.get("visual"))
        if scene_text:
            layers["scene_setting"] = scene_text
            panel["scene_setting"] = scene_text
    if not _nonempty(panel.get("connective_prose")) and not _string_list(layers.get("connective_prose")):
        connective = _nonempty(panel.get("narration")) or _nonempty(scene.get("callback_to_spine_event"))
        if connective:
            layers["connective_prose"] = connective
            panel["connective_prose"] = connective
    if not _nonempty(panel.get("reality_mapping")) and not _string_list(layers.get("reality_mapping")):
        reality = _nonempty(panel.get("life_scene"))
        if reality:
            layers["reality_mapping"] = reality
            panel["reality_mapping"] = reality
    if not _nonempty(panel.get("interior_monologue")) and not _string_list(layers.get("interior_monologue")) and role in {"reaction", "turn", "payoff"}:
        emotion = _nonempty(panel.get("emotion"))
        if emotion:
            layers["interior_monologue"] = f"他/她的反应：{emotion}"
            panel["interior_monologue"] = layers["interior_monologue"]
    panel["text_layers"] = layers

    card_form = panel_card_form_lines(panel)
    if not card_form:
        card_form = _dedupe([*(dialogue[:1]), _nonempty(panel.get("narration")), _nonempty(panel.get("reality_mapping"))])[:3]
    long_form = panel_long_form_lines(panel)
    panel["text_variants"] = {
        "long_form": long_form,
        "card_form": card_form[:3],
    }
    panel["copy_jobs"] = _copy_jobs(panel, role)
    panel["text_requirements"] = {
        "language": "zh-CN",
        "long_form": "用于长图、review 和生产叙事；允许写足场景、心理、因果和概念翻译。",
        "card_form": "用于手机单格卡片；最多三段：角色台词 / 大白话解释 / 现实映射。",
        "inner_monologue_applicable": role in {"reaction", "turn", "payoff"},
        "max_card_paragraphs": 3,
    }


def _copy_jobs(panel: dict[str, Any], role: str) -> list[str]:
    jobs = ["scene_setting", "plain_language_translation", "cause_effect_bridge"]
    if _string_list(panel.get("dialogue")):
        jobs.insert(0, "character_voice")
    if role in {"reaction", "turn", "payoff"}:
        jobs.append("interior_monologue")
    if _nonempty(panel.get("life_scene")):
        jobs.append("reality_mapping")
    if role == "payoff":
        jobs.append("theme_close_and_series_hook")
    return _dedupe(jobs)


def _text_budgets(panel: dict[str, Any]) -> dict[str, dict[str, int]]:
    metrics = panel_text_metrics(panel)
    shot_size = _nonempty(panel.get("shot_size"))
    return {
        "card_form": {
            "max_chars": CARD_TEXT_BUDGET_BY_SHOT.get(shot_size, 48),
            "actual_chars": int(metrics["card_form_chars"]),
        },
        "long_form": {
            "max_chars": LONG_FORM_BUDGET_BY_SHOT.get(shot_size, 150),
            "actual_chars": int(metrics["long_form_chars"]),
        },
    }


def _drawable_missing(panel: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if _nonempty(panel.get("panel_role")) not in ALLOWED_PANEL_ROLES:
        missing.append("panel_role")
    if not _nonempty(panel.get("action_verb")):
        missing.append("action_verb")
    if not isinstance(panel.get("reading_order"), int) or panel.get("reading_order") <= 0:
        missing.append("reading_order")
    budget = panel.get("balloon_budget")
    if not isinstance(budget, dict) or not isinstance(budget.get("max_chars"), int) or not isinstance(budget.get("actual_chars"), int):
        missing.append("balloon_budget")
    return missing


def _is_balloon_overflow(value: object) -> bool:
    return isinstance(value, dict) and isinstance(value.get("max_chars"), int) and isinstance(value.get("actual_chars"), int) and value["actual_chars"] > value["max_chars"]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_nonempty(item) for item in value if _nonempty(item)]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _nonempty(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _excerpt(text: str, limit: int = 120) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    return clean if len(clean) <= limit else clean[: limit - 1].rstrip() + "…"


def _int_or_zero(value: object) -> int:
    return value if isinstance(value, int) and value >= 0 else 0


def _project_relative(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _nonempty(value: object) -> str:
    return "" if value is None else str(value).strip()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
