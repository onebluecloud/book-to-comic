from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any


ALLOWED_ENVIRONMENT_KINDS = {
    "life_scene",
    "discourse",
    "metaphor",
    "source_world",
    "historical_reconstruction",
    "institutional_process",
    "material_detail",
}
ALLOWED_GROUNDING_TYPES = {
    "contemporary_life",
    "historical_reconstruction",
    "institutional_process",
    "source_world",
    "material_detail",
    "analogy",
    "counterexample",
    "diagrammatic",
}
ALLOWED_SHOT_SIZES = {"establishing", "wide", "medium", "close-up", "insert", "over-shoulder", "insert/over-shoulder"}
ALLOWED_CONTINUITY = {
    "same-scene-push-in",
    "next-action-beat",
    "reaction-shot",
    "cause-effect",
    "match-cut",
    "scene-transition",
}
ALLOWED_ESCALATION_ROLES = {"setup", "complication", "crisis", "turn-and-action"}
ALLOWED_PANEL_ROLES = {"establishing", "action", "reaction", "turn", "insert", "transition", "payoff"}
ALLOWED_ANCHOR_SUBJECTS = {"human_face", "body_reaction", "fateful_moment"}
ALLOWED_HOOK_TYPES = {"conflict", "mystery", "contrast", "stakes"}
MIN_SOURCE_COVERAGE = 0.9
MAX_BALLOON_OVERFLOW_RATE = 0.01


class StoryGateError(ValueError):
    def __init__(self, message: str, report: dict[str, Any]):
        super().__init__(message)
        self.report = report


def validate_story_gate(
    project: str | Path,
    *,
    require_llm_gate: bool = False,
    expected_panel_count: int | None = None,
) -> dict[str, Any]:
    root = Path(project)
    episode_path = root / "story" / "episode-001.json"
    environment_path = root / "planning" / "environment_bible.json"
    report_path = root / "qa" / "story-gate-report.json"

    previous_report = _read_json(report_path) if report_path.exists() else {}
    llm_gate = previous_report.get("llm_gate") if isinstance(previous_report.get("llm_gate"), dict) else None
    if llm_gate is None:
        llm_gate = {
            "status": "required",
            "checks": [
                "中文叠字校对",
                "证据链 source coverage 复核",
                "叙事连续性打乱测试",
                "可画性分镜/气泡预算复核",
                "场景多样性复核",
            ],
            "issues": [],
        }

    issues: list[dict[str, str]] = []
    episode = _read_required_json(episode_path, issues)
    environments = _read_required_json(environment_path, issues)
    project_data = _read_optional_json(root / "project.json")
    delivery_intent = _nonempty(project_data.get("delivery_intent")) or "hardcore_showcase"

    env_kind_by_id = _environment_kind_map(environments, issues)
    scenes = episode.get("scenes") if isinstance(episode, dict) else None
    root_panels = episode.get("panels") if isinstance(episode, dict) else None

    if isinstance(episode, dict):
        _check_titles_clean(episode, project_data, issues)
        _check_mass_traffic_style(root, episode, delivery_intent, issues)
    if isinstance(episode, dict) and str(episode.get("episode_id", "")).upper() == "WHOLE-BOOK":
        _issue(issues, "episode_id", "story/episode-001.json", "episode_id cannot be WHOLE-BOOK; split the book into real episodes.")
    if isinstance(episode, dict) and "panels" in episode:
        _issue(issues, "flat-panels", "story/episode-001.json.panels", "episode root panels[] must not drive final comics; use scenes[].panels[] so panels form narrative scenes.")
    if not _has_complete_narrative_spine(episode):
        _issue(
            issues,
            "narrative-spine",
            "story/episode-001.json.narrative_spine",
            "narrative_spine must include protagonist, opening_struggle, and this_episode_change.",
        )
    _validate_adaptation_strategy(episode, issues)
    _validate_dramatic_spine(episode, issues)
    _validate_story_ir(episode, issues)
    if not isinstance(scenes, list) or not scenes:
        _issue(issues, "missing-scenes", "story/episode-001.json.scenes", "scenes[] is required; an episode cannot be a flat point-card list.")
        scenes = []
    is_schema3 = isinstance(episode, dict) and str(episode.get("schema_version")) == "3.0"
    min_scenes = 2 if is_schema3 else 3
    if len(scenes) < min_scenes:
        _issue(issues, "scene-count", "story/episode-001.json.scenes", f"Each formal episode must contain at least {min_scenes} scenes.")
    scene_removal_test: list[dict[str, Any]] = []
    rhythm_warnings: list[dict[str, str]] = []
    if is_schema3:
        scene_removal_test = _validate_schema3_story_core(episode, scenes, issues)

    scene_kinds: list[str] = []
    scene_locations: list[str] = []
    escalation_roles: list[str] = []
    panel_count = 0
    emotional_anchor_count = 0
    panels_with_source_refs = 0
    panels_with_drawable_contract = 0
    balloon_overflow_count = 0
    reading_orders: list[int] = []
    for scene_index, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            _issue(issues, "scene-type", f"story/episode-001.json.scenes[{scene_index}]", "Each scene must be an object.")
            continue
        location = _nonempty(scene.get("location"))
        if not location:
            _issue(issues, "scene-location", f"story/episode-001.json.scenes[{scene_index}].location", "Each scene must declare a location.")
            location = f"scene-{scene_index + 1}"
        scene_locations.append(location)
        kind = _nonempty(scene.get("kind")) or env_kind_by_id.get(location, "")
        if not kind:
            _issue(issues, "scene-kind", f"story/episode-001.json.scenes[{scene_index}].location", f"Scene location `{location}` must resolve to a supported environment kind.")
        elif kind not in ALLOWED_ENVIRONMENT_KINDS:
            _issue(issues, "scene-kind", f"story/episode-001.json.scenes[{scene_index}].kind", f"Unsupported scene kind `{kind}`.")
        else:
            scene_kinds.append(kind)
        escalation_role = _nonempty(scene.get("escalation_role"))
        if not escalation_role:
            _issue(issues, "scene-escalation-role", f"story/episode-001.json.scenes[{scene_index}].escalation_role", "Each scene needs escalation_role so scenes form a rising story arc, not parallel vignettes.")
        elif escalation_role not in ALLOWED_ESCALATION_ROLES:
            _issue(issues, "scene-escalation-role", f"story/episode-001.json.scenes[{scene_index}].escalation_role", f"Unsupported escalation_role `{escalation_role}`.")
        else:
            escalation_roles.append(escalation_role)
        if not _nonempty(scene.get("callback_to_spine_event")):
            _issue(issues, "scene-spine-callback", f"story/episode-001.json.scenes[{scene_index}].callback_to_spine_event", "Each scene must callback to the episode spine_event; otherwise it is a detachable point vignette.")
        is_last_scene = scene_index == len(scenes) - 1
        if (is_last_scene or escalation_role == "turn-and-action") and not _nonempty(scene.get("change_shown_by_action")):
            _issue(issues, "scene-action-ending", f"story/episode-001.json.scenes[{scene_index}].change_shown_by_action", "The final/turn scene must show the protagonist's change through a concrete action, not only a stated lesson.")

        panels = scene.get("panels")
        if not isinstance(panels, list) or not panels:
            _issue(issues, "scene-panels", f"story/episode-001.json.scenes[{scene_index}].panels", "Each scene must contain panels[].")
            continue
        panel_count += len(panels)
        shot_sizes: set[str] = set()
        for panel_index, panel in enumerate(panels):
            if not isinstance(panel, dict):
                _issue(issues, "panel-type", f"story/episode-001.json.scenes[{scene_index}].panels[{panel_index}]", "Each panel must be an object.")
                continue
            panel_path = f"story/episode-001.json.scenes[{scene_index}].panels[{panel_index}]"
            has_source_refs = _has_nonempty_string_list(panel.get("source_refs"))
            if has_source_refs:
                panels_with_source_refs += 1
            else:
                _issue(issues, "panel-source-refs", f"{panel_path}.source_refs", "Each panel must carry source_refs back to story_ir.source_chunks; evidence cannot stop at episode level.")

            role = _nonempty(panel.get("panel_role"))
            role_ok = False
            if not role:
                _issue(issues, "panel-role", f"{panel_path}.panel_role", "Each panel needs panel_role so it has a job in the comic sequence, not just a nice image.")
            elif role not in ALLOWED_PANEL_ROLES:
                _issue(issues, "panel-role", f"{panel_path}.panel_role", f"Unsupported panel_role `{role}`.")
            else:
                role_ok = True

            action_verb_ok = bool(_nonempty(panel.get("action_verb")))
            if not action_verb_ok:
                _issue(issues, "panel-action-verb", f"{panel_path}.action_verb", "Each panel needs a drawable action_verb; abstract explanation is not enough.")

            reading_order_ok = _validate_reading_order_value(panel.get("reading_order"), panel_path, issues)
            if reading_order_ok is not None:
                reading_orders.append(reading_order_ok)

            balloon_ok, overflow = _validate_balloon_budget(panel.get("balloon_budget"), panel_path, issues)
            if overflow:
                balloon_overflow_count += 1
            if role_ok and action_verb_ok and reading_order_ok is not None and balloon_ok:
                panels_with_drawable_contract += 1

            shot_size = _nonempty(panel.get("shot_size"))
            if not shot_size:
                _issue(issues, "shot-size", _panel_path(scene_index, panel_index, "shot_size"), "shot_size is required.")
            elif shot_size not in ALLOWED_SHOT_SIZES:
                _issue(issues, "shot-size", _panel_path(scene_index, panel_index, "shot_size"), f"Unsupported shot_size `{shot_size}`.")
            else:
                shot_sizes.add(shot_size)
            if panel.get("emotional_anchor") is True:
                emotional_anchor_count += 1
                anchor_subject = _nonempty(panel.get("anchor_subject"))
                if anchor_subject not in ALLOWED_ANCHOR_SUBJECTS:
                    _issue(issues, "emotional-anchor-subject", f"{panel_path}.anchor_subject", "emotional anchor must use human_face, body_reaction, or fateful_moment.")
                if role not in {"reaction", "turn", "payoff"}:
                    _issue(issues, "emotional-anchor-role", f"{panel_path}.panel_role", "emotional_anchor panels must be reaction, turn, or payoff beats.")
                if shot_size not in {"close-up", "medium"}:
                    _issue(issues, "emotional-anchor-shot", f"{panel_path}.shot_size", "emotional_anchor panels must use close-up or medium shot_size.")
                if not _nonempty(panel.get("anchor_note")):
                    _issue(issues, "emotional-anchor-note", f"{panel_path}.anchor_note", "emotional_anchor panels need anchor_note explaining why the image stops readers.")
            grounding = panel.get("grounding")
            if isinstance(grounding, dict):
                grounding_type = _nonempty(grounding.get("type") or grounding.get("mode"))
                if grounding_type not in ALLOWED_GROUNDING_TYPES:
                    _issue(issues, "grounding-type", _panel_path(scene_index, panel_index, "grounding.type"), f"Unsupported grounding.type `{grounding_type}`.")
            elif not _nonempty(panel.get("life_scene")):
                _issue(issues, "panel-grounding", _panel_path(scene_index, panel_index, "grounding"), "Each panel must map the concept to a concrete grounding object.")
            continuity = panel.get("continuity_from_prev")
            if panel_index == 0:
                if _nonempty(continuity) and continuity not in ALLOWED_CONTINUITY:
                    _issue(issues, "continuity", _panel_path(scene_index, panel_index, "continuity_from_prev"), f"Unsupported continuity_from_prev `{continuity}`.")
            else:
                if not _nonempty(continuity):
                    _issue(issues, "continuity", _panel_path(scene_index, panel_index, "continuity_from_prev"), "continuity_from_prev is required except on the first panel of each scene.")
                elif continuity not in ALLOWED_CONTINUITY:
                    _issue(issues, "continuity", _panel_path(scene_index, panel_index, "continuity_from_prev"), f"Unsupported continuity_from_prev `{continuity}`.")
        if len(panels) >= 3 and len(shot_sizes) < 3:
            _issue(issues, "shot-variety", f"story/episode-001.json.scenes[{scene_index}].panels", "Each scene must use at least 3 shot_size values.")

    source_coverage = panels_with_source_refs / panel_count if panel_count else 0.0
    drawable_panel_rate = panels_with_drawable_contract / panel_count if panel_count else 0.0
    balloon_overflow_rate = balloon_overflow_count / panel_count if panel_count else 0.0
    reading_order_passed = _validate_reading_order_sequence(reading_orders, panel_count, issues)
    if panel_count and source_coverage < MIN_SOURCE_COVERAGE:
        _issue(
            issues,
            "source-coverage",
            "story/episode-001.json.scenes[].panels[].source_refs",
            f"Source Coverage must be >= {MIN_SOURCE_COVERAGE:.2f}; got {source_coverage:.2f}.",
        )
    if panel_count and balloon_overflow_rate > MAX_BALLOON_OVERFLOW_RATE:
        _issue(
            issues,
            "balloon-overflow-rate",
            "story/episode-001.json.scenes[].panels[].balloon_budget",
            f"Balloon Overflow Rate must be <= {MAX_BALLOON_OVERFLOW_RATE:.2f}; got {balloon_overflow_rate:.2f}.",
        )

    life_scene_count = sum(1 for kind in scene_kinds if kind == "life_scene")
    if scene_locations:
        location, count = Counter(scene_locations).most_common(1)[0]
        if count / len(scene_locations) > 0.5:
            _issue(issues, "scene-dominance", "story/episode-001.json.scenes", f"Single location `{location}` appears in more than 50% of scenes.")
    if scenes and escalation_roles:
        if escalation_roles[0] != "setup":
            _issue(issues, "scene-escalation-order", "story/episode-001.json.scenes[0].escalation_role", "The first scene must set up the episode spine event.")
        if escalation_roles[-1] != "turn-and-action":
            _issue(issues, "scene-escalation-order", f"story/episode-001.json.scenes[{len(scenes) - 1}].escalation_role", "The final scene must be turn-and-action so the episode ends with visible change.")
        if len(set(escalation_roles)) < min(3, len(scenes)):
            _issue(issues, "scene-escalation-variety", "story/episode-001.json.scenes", "Scene escalation roles must vary; parallel scenes are not a story arc.")
    if expected_panel_count is not None and panel_count != expected_panel_count:
        _issue(
            issues,
            "panel-count",
            "story/episode-001.json.scenes",
            f"Story panel count ({panel_count}) must equal approved panel assets ({expected_panel_count}).",
        )
    rhythm_metrics: dict[str, Any] = {}
    if is_schema3:
        _validate_opening_hook(flatten_episode_panels(episode), issues)
        required_anchor_count = 2 if delivery_intent == "mass_traffic" else 1
        if emotional_anchor_count < required_anchor_count:
            _issue(
                issues,
                "emotional-anchor-count",
                "story/episode-001.json.scenes[].panels[].emotional_anchor",
                f"Episode needs at least {required_anchor_count} emotional_anchor panel(s) for delivery_intent={delivery_intent}; got {emotional_anchor_count}.",
            )
        rhythm_metrics = _validate_schema3_rhythm(episode, flatten_episode_panels(episode), issues, rhythm_warnings)

    if require_llm_gate:
        _validate_llm_gate(llm_gate, issues, root)

    deterministic = {
        "passed": not issues,
        "issues": issues,
        "scene_count": len(scenes),
        "life_scene_count": life_scene_count,
        "grounding_modes": _grounding_mode_counts(flatten_episode_panels(episode)),
        "panel_count": panel_count,
        "scene_locations": scene_locations,
        "quality_metrics": {
            "source_coverage": round(source_coverage, 4),
            "drawable_panel_rate": round(drawable_panel_rate, 4),
            "balloon_overflow_rate": round(balloon_overflow_rate, 4),
            "reading_order_passed": reading_order_passed,
            "emotional_anchor_count": emotional_anchor_count,
            "required_emotional_anchor_count": 2 if delivery_intent == "mass_traffic" else 1,
        },
        "scene_removal_test": scene_removal_test,
        "rhythm": rhythm_metrics,
        "rhythm_warnings": rhythm_warnings,
        "allowed_shot_sizes": sorted(ALLOWED_SHOT_SIZES),
        "allowed_continuity_from_prev": sorted(ALLOWED_CONTINUITY),
        "allowed_escalation_roles": sorted(ALLOWED_ESCALATION_ROLES),
        "allowed_panel_roles": sorted(ALLOWED_PANEL_ROLES),
        "allowed_anchor_subjects": sorted(ALLOWED_ANCHOR_SUBJECTS),
        "allowed_hook_types": sorted(ALLOWED_HOOK_TYPES),
        "delivery_intent": delivery_intent,
    }
    report = {
        "schema_version": "2.0",
        "updated_at": _now(),
        "deterministic_gate": deterministic,
        "llm_gate": llm_gate,
    }
    _write_json(report_path, report)
    if issues:
        raise StoryGateError(f"Story gate failed with {len(issues)} issue(s)", report)
    return report


def flatten_episode_panels(episode: dict[str, Any]) -> list[dict[str, Any]]:
    scenes = episode.get("scenes")
    if isinstance(scenes, list) and scenes:
        panels: list[dict[str, Any]] = []
        for scene in scenes:
            if not isinstance(scene, dict):
                continue
            for panel in scene.get("panels", []):
                if isinstance(panel, dict):
                    panels.append(panel)
        return panels
    panels = episode.get("panels", [])
    return [panel for panel in panels if isinstance(panel, dict)] if isinstance(panels, list) else []


def _validate_schema3_story_core(
    episode: dict[str, Any],
    scenes: list[Any],
    issues: list[dict[str, str]],
) -> list[dict[str, Any]]:
    concept_ids = {
        _nonempty(unit.get("concept_id") or unit.get("id"))
        for unit in episode.get("concept_units", [])
        if isinstance(unit, dict) and _nonempty(unit.get("concept_id") or unit.get("id"))
    }
    spine_event = episode.get("narrative_spine", {}).get("spine_event", {}) if isinstance(episode.get("narrative_spine"), dict) else {}
    trigger = _nonempty(spine_event.get("trigger")) if isinstance(spine_event, dict) else ""
    removal: list[dict[str, Any]] = []
    signatures: Counter[str] = Counter()
    previous_consequence = trigger

    required_text_fields = (
        "scene_id",
        "location",
        "kind",
        "story_function",
        "cause_from_previous",
        "character_goal",
        "obstacle",
        "attempt",
        "turn",
        "decision",
        "consequence",
        "stakes_before",
        "stakes_after",
        "new_information",
        "irreversible_change",
        "unremovable_reason",
    )
    for index, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue
        scene_id = _nonempty(scene.get("scene_id")) or f"S{index + 1:02d}"
        path = f"story/episode-001.json.scenes[{index}]"
        for field in required_text_fields:
            if not _nonempty(scene.get(field)):
                _issue(issues, "scene-required-field", f"{path}.{field}", f"schema 3.0 scene.{field} is required.")

        cause = _nonempty(scene.get("cause_from_previous"))
        if index == 0:
            if trigger and not _references_text(cause, trigger):
                _issue(issues, "spine-trigger", f"{path}.cause_from_previous", "First scene cause_from_previous must explain narrative_spine.spine_event.trigger.")
        elif previous_consequence and not _references_text(cause, previous_consequence):
            _issue(issues, "scene-causality", f"{path}.cause_from_previous", "Non-first scene cause_from_previous must reference the previous scene consequence.")

        stakes_before = _nonempty(scene.get("stakes_before"))
        stakes_after = _nonempty(scene.get("stakes_after"))
        if stakes_before and stakes_after and stakes_before == stakes_after:
            _issue(issues, "stakes-change", f"{path}.stakes_after", "stakes_after must differ from stakes_before.")

        decision = _nonempty(scene.get("decision"))
        consequence = _nonempty(scene.get("consequence"))
        if decision and not consequence:
            _issue(issues, "decision-consequence", f"{path}.consequence", "Every decision must produce a consequence.")
        if consequence:
            previous_consequence = consequence

        reason = _nonempty(scene.get("unremovable_reason"))
        reason_passed = _substantive_unremovable_reason(reason)
        if not reason_passed:
            _issue(issues, "scene-removal-test", f"{path}.unremovable_reason", "unremovable_reason must explain what causal link breaks if the scene is removed.")
        removal.append({"scene_id": scene_id, "passed": reason_passed, "reason": reason})

        concepts = _string_list(scene.get("concept_carried"))
        if not concepts:
            _issue(issues, "concept-carried", f"{path}.concept_carried", "Each scene must carry at least one concept unit id.")
        elif concept_ids:
            unknown = sorted(set(concepts) - concept_ids)
            if unknown:
                _issue(issues, "concept-carried", f"{path}.concept_carried", f"Unknown concept unit ids: {unknown}.")

        if not _has_nonempty_string_list(scene.get("source_refs")):
            _issue(issues, "scene-source-refs", f"{path}.source_refs", "Each scene must carry source_refs.")

        emotion_arc = scene.get("emotion_arc")
        if not isinstance(emotion_arc, dict) or not emotion_arc:
            _issue(issues, "emotion-arc", f"{path}.emotion_arc", "Each scene needs an emotion_arc shown through action, body, expression, distance, or props.")

        signature = "|".join(
            _token_signature(scene.get(field))
            for field in ("location", "concept_carried", "character_goal", "obstacle", "turn")
        )
        signatures[signature] += 1

    for signature, count in signatures.items():
        if signature and count > 1:
            _issue(issues, "duplicate-scene", "story/episode-001.json.scenes", "Two scenes share the same dramatic function signature; one is likely removable.")

    if scenes:
        last = scenes[-1]
        if isinstance(last, dict) and not (
            _substantive_text(last.get("change_shown_by_action")) or _substantive_text(last.get("irreversible_change"))
        ):
            _issue(issues, "last-action", f"story/episode-001.json.scenes[{len(scenes) - 1}]", "Last scene must end in a visible irreversible action.")
    return removal


def _validate_schema3_rhythm(
    episode: dict[str, Any],
    panels: list[dict[str, Any]],
    issues: list[dict[str, str]],
    warnings: list[dict[str, str]],
) -> dict[str, Any]:
    episode_format = _nonempty(episode.get("episode_format")) or "standard"
    ranges = {
        "short_hook": (4, 6, 2, 3),
        "standard": (6, 10, 3, 5),
        "deep_scene": (10, 16, 3, 6),
    }
    if episode_format not in ranges:
        _issue(issues, "episode-format", "story/episode-001.json.episode_format", "episode_format must be short_hook, standard, or deep_scene.")
        episode_format = "standard"
    min_panels, max_panels, min_scenes, max_scenes = ranges[episode_format]
    scene_count = len(episode.get("scenes", [])) if isinstance(episode.get("scenes"), list) else 0
    panel_count = len(panels)
    if not min_panels <= panel_count <= max_panels:
        _issue(
            issues,
            "episode-format-panel-count",
            "story/episode-001.json.scenes[].panels",
            f"{episode_format} must contain {min_panels}-{max_panels} panels; got {panel_count}.",
        )
    if not min_scenes <= scene_count <= max_scenes:
        _issue(
            issues,
            "episode-format-scene-count",
            "story/episode-001.json.scenes",
            f"{episode_format} must contain {min_scenes}-{max_scenes} scenes; got {scene_count}.",
        )

    required_panel_fields = (
        "beat_duration",
        "visual_density",
        "text_density",
        "visual_weight",
        "pause_after",
        "reveal_priority",
        "layout_hint",
    )
    shot_sequence: list[str] = []
    role_sequence: list[str] = []
    dense_sequence: list[bool] = []
    climax_panels: list[str] = []
    shot_values: set[str] = set()
    for index, panel in enumerate(panels):
        panel_id = _nonempty(panel.get("panel_id")) or f"P{index + 1:02d}"
        panel_path = f"story/episode-001.json.scenes[].panels[{index}]"
        for field in required_panel_fields:
            value = panel.get(field)
            if field == "pause_after":
                if not isinstance(value, bool):
                    _issue(issues, "rhythm-panel-field", f"{panel_path}.{field}", "pause_after must be boolean.")
            elif not _nonempty(value):
                _issue(issues, "rhythm-panel-field", f"{panel_path}.{field}", f"{field} is required.")

        shot = _nonempty(panel.get("shot_size"))
        role = _nonempty(panel.get("panel_role"))
        visual_density = _nonempty(panel.get("visual_density")).lower()
        text_density = _nonempty(panel.get("text_density")).lower()
        reveal = _nonempty(panel.get("reveal_priority")).lower()
        visual_weight = _nonempty(panel.get("visual_weight")).lower()
        emotion = _nonempty(panel.get("emotion")).lower()
        shot_sequence.append(shot)
        role_sequence.append(role)
        if shot:
            shot_values.add(shot)
        dense = visual_density in {"dense", "high"} or text_density in {"dense", "high"}
        dense_sequence.append(dense)
        if dense and index + 1 < len(panels):
            next_panel = panels[index + 1]
            next_visual = _nonempty(next_panel.get("visual_density")).lower()
            next_text = _nonempty(next_panel.get("text_density")).lower()
            if next_visual not in {"low", "breathing"} and next_text not in {"low", "breathing"}:
                warnings.append({"code": "dense-needs-breathing", "path": panel_path, "message": "Dense panel should be followed by a breathing panel."})
        if panel.get("pause_after") is True and text_density not in {"low", "breathing"}:
            _issue(issues, "rhythm-pause-text", f"{panel_path}.text_density", "pause_after panels must use low text density.")
        if reveal == "climax":
            climax_panels.append(panel_id)
            high_tension = any(token in emotion for token in ("高", "紧", "crisis", "high", "tension", "climax"))
            if visual_weight not in {"large", "hero"} or not high_tension:
                _issue(issues, "rhythm-climax", panel_path, "Climax panel must use large/hero visual_weight and high tension emotion.")

    _validate_no_three_same(shot_sequence, "rhythm-shot-variety", "shot_size", issues)
    _validate_no_three_same(role_sequence, "rhythm-role-variety", "panel_role", issues)
    for index in range(len(dense_sequence) - 2):
        if dense_sequence[index] and dense_sequence[index + 1] and dense_sequence[index + 2]:
            _issue(issues, "rhythm-density", "story/episode-001.json.scenes[].panels", "Do not place three dense panels in a row.")
            break
    if panel_count >= 6 and len(shot_values) < 3:
        _issue(issues, "rhythm-dynamic-shot-variety", "story/episode-001.json.scenes[].panels[].shot_size", "Episode needs at least three shot sizes.")
    if not climax_panels and panels:
        _issue(issues, "rhythm-climax", "story/episode-001.json.rhythm_plan", "Episode rhythm must mark a climax panel with reveal_priority=climax.")

    return {
        "episode_format": episode_format,
        "scene_count": scene_count,
        "panel_count": panel_count,
        "climax_panels": climax_panels,
        "shot_variety": len(shot_values),
    }


def _read_required_json(path: Path, issues: list[dict[str, str]]) -> dict[str, Any]:
    if not path.exists():
        _issue(issues, "missing-file", str(path), f"Required file is missing: {path.name}")
        return {}
    try:
        return _read_json(path)
    except json.JSONDecodeError as exc:
        _issue(issues, "invalid-json", str(path), f"Invalid JSON: {exc}")
        return {}


def _environment_kind_map(data: dict[str, Any], issues: list[dict[str, str]]) -> dict[str, str]:
    result: dict[str, str] = {}
    environments = data.get("environments", [])
    if not isinstance(environments, list):
        _issue(issues, "environment-bible", "planning/environment_bible.json.environments", "environments must be a list.")
        return result
    for index, environment in enumerate(environments):
        if not isinstance(environment, dict):
            _issue(issues, "environment-type", f"planning/environment_bible.json.environments[{index}]", "Each environment must be an object.")
            continue
        kind = _nonempty(environment.get("kind"))
        if kind not in ALLOWED_ENVIRONMENT_KINDS:
            _issue(issues, "environment-kind", f"planning/environment_bible.json.environments[{index}].kind", "Environment kind must be supported by the official grounding system.")
            continue
        for key in ("id", "name"):
            value = _nonempty(environment.get(key))
            if value:
                result[value] = kind
    return result


def _has_complete_narrative_spine(episode: object) -> bool:
    if not isinstance(episode, dict):
        return False
    spine = episode.get("narrative_spine")
    if not isinstance(spine, dict):
        return False
    return all(_nonempty(spine.get(key)) for key in ("protagonist", "opening_struggle", "this_episode_change"))


def _validate_adaptation_strategy(episode: object, issues: list[dict[str, str]]) -> None:
    if not isinstance(episode, dict):
        return
    strategy = episode.get("adaptation_strategy")
    if not isinstance(strategy, dict):
        _issue(issues, "adaptation-strategy", "story/episode-001.json.adaptation_strategy", "adaptation_strategy is required before narrative_spine: soul_conflict, chosen_form, why_fits, avoided_cliches, novelty_hook.")
        return
    for key in ("soul_conflict", "chosen_form", "why_fits", "novelty_hook"):
        if not _nonempty(strategy.get(key)):
            _issue(issues, "adaptation-strategy", f"story/episode-001.json.adaptation_strategy.{key}", f"adaptation_strategy.{key} is required.")
    avoided = strategy.get("avoided_cliches")
    if not isinstance(avoided, list) or len([item for item in avoided if _nonempty(item)]) < 3:
        _issue(issues, "adaptation-strategy", "story/episode-001.json.adaptation_strategy.avoided_cliches", "adaptation_strategy.avoided_cliches must list at least 3 cliches to avoid.")


def _validate_dramatic_spine(episode: object, issues: list[dict[str, str]]) -> None:
    if not isinstance(episode, dict):
        return
    spine = episode.get("narrative_spine")
    if not isinstance(spine, dict):
        return
    if not _nonempty(spine.get("foil")):
        _issue(issues, "narrative-spine-foil", "story/episode-001.json.narrative_spine.foil", "narrative_spine.foil is required so the episode has a concrete opposing relationship, not only an abstract idea.")
    event = spine.get("spine_event")
    if not isinstance(event, dict):
        _issue(issues, "narrative-spine-event", "story/episode-001.json.narrative_spine.spine_event", "narrative_spine.spine_event is required: one concrete event with stakes and a trigger must run through the episode.")
        return
    for key in ("what", "stakes", "trigger"):
        if not _nonempty(event.get(key)):
            _issue(issues, "narrative-spine-event", f"story/episode-001.json.narrative_spine.spine_event.{key}", f"narrative_spine.spine_event.{key} is required.")


def _validate_story_ir(episode: object, issues: list[dict[str, str]]) -> None:
    if not isinstance(episode, dict):
        return
    story_ir = episode.get("story_ir")
    if not isinstance(story_ir, dict):
        _issue(
            issues,
            "story-ir",
            "story/episode-001.json.story_ir",
            "story_ir is required: source_chunks -> scene_beats -> panel_scripts must preserve evidence before drawing.",
        )
        return

    source_chunks = story_ir.get("source_chunks")
    scene_beats = story_ir.get("scene_beats")
    panel_scripts = story_ir.get("panel_scripts")
    source_ids = _validate_source_chunks(source_chunks, issues)
    beat_ids = _validate_scene_beats(scene_beats, source_ids, issues)
    _validate_panel_scripts(panel_scripts, beat_ids, source_ids, issues)
    scene_beat_items = scene_beats if isinstance(scene_beats, list) else []
    panel_script_items = panel_scripts if isinstance(panel_scripts, list) else []

    scene_ids = {
        _nonempty(scene.get("scene_id"))
        for scene in episode.get("scenes", [])
        if isinstance(scene, dict) and _nonempty(scene.get("scene_id"))
    }
    beat_scene_ids = {
        _nonempty(beat.get("scene_id"))
        for beat in scene_beat_items
        if isinstance(beat, dict) and _nonempty(beat.get("scene_id"))
    }
    missing_scene_beats = scene_ids - beat_scene_ids
    if missing_scene_beats:
        _issue(
            issues,
            "story-ir-coverage",
            "story/episode-001.json.story_ir.scene_beats",
            f"story_ir.scene_beats must cover every scene_id; missing {sorted(missing_scene_beats)}.",
        )

    panel_ids = {
        _nonempty(panel.get("panel_id"))
        for panel in flatten_episode_panels(episode)
        if _nonempty(panel.get("panel_id"))
    }
    script_panel_ids = {
        _nonempty(script.get("panel_id"))
        for script in panel_script_items
        if isinstance(script, dict) and _nonempty(script.get("panel_id"))
    }
    missing_panel_scripts = panel_ids - script_panel_ids
    if missing_panel_scripts:
        _issue(
            issues,
            "story-ir-coverage",
            "story/episode-001.json.story_ir.panel_scripts",
            f"story_ir.panel_scripts must cover every panel_id; missing {sorted(missing_panel_scripts)}.",
        )


def _validate_source_chunks(source_chunks: object, issues: list[dict[str, str]]) -> set[str]:
    source_ids: set[str] = set()
    if not isinstance(source_chunks, list) or not source_chunks:
        _issue(issues, "story-ir", "story/episode-001.json.story_ir.source_chunks", "story_ir.source_chunks must be a non-empty list.")
        return source_ids
    for index, chunk in enumerate(source_chunks):
        path = f"story/episode-001.json.story_ir.source_chunks[{index}]"
        if not isinstance(chunk, dict):
            _issue(issues, "story-ir-source-chunk", path, "Each source chunk must be an object.")
            continue
        for key in ("chunk_id", "chapter_id", "paragraph_start", "paragraph_end", "text_excerpt"):
            value = chunk.get(key)
            if key.startswith("paragraph_"):
                if not isinstance(value, int) or value < 0:
                    _issue(issues, "story-ir-source-chunk", f"{path}.{key}", f"source_chunks[].{key} must be a non-negative integer.")
            elif not _nonempty(value):
                _issue(issues, "story-ir-source-chunk", f"{path}.{key}", f"source_chunks[].{key} is required.")
        chunk_id = _nonempty(chunk.get("chunk_id"))
        if chunk_id:
            source_ids.add(chunk_id)
    return source_ids


def _validate_scene_beats(scene_beats: object, source_ids: set[str], issues: list[dict[str, str]]) -> set[str]:
    beat_ids: set[str] = set()
    if not isinstance(scene_beats, list) or not scene_beats:
        _issue(issues, "story-ir", "story/episode-001.json.story_ir.scene_beats", "story_ir.scene_beats must be a non-empty list.")
        return beat_ids
    for index, beat in enumerate(scene_beats):
        path = f"story/episode-001.json.story_ir.scene_beats[{index}]"
        if not isinstance(beat, dict):
            _issue(issues, "story-ir-scene-beat", path, "Each scene beat must be an object.")
            continue
        for key in ("beat_id", "scene_id", "goal", "obstacle", "turn", "visual_hook"):
            if not _nonempty(beat.get(key)):
                _issue(issues, "story-ir-scene-beat", f"{path}.{key}", f"scene_beats[].{key} is required.")
        beat_id = _nonempty(beat.get("beat_id"))
        if beat_id:
            beat_ids.add(beat_id)
        _validate_source_ref_list(beat.get("source_refs"), source_ids, f"{path}.source_refs", "story-ir-scene-beat", issues)
    return beat_ids


def _validate_panel_scripts(
    panel_scripts: object,
    beat_ids: set[str],
    source_ids: set[str],
    issues: list[dict[str, str]],
) -> None:
    if not isinstance(panel_scripts, list) or not panel_scripts:
        _issue(issues, "story-ir", "story/episode-001.json.story_ir.panel_scripts", "story_ir.panel_scripts must be a non-empty list.")
        return
    for index, script in enumerate(panel_scripts):
        path = f"story/episode-001.json.story_ir.panel_scripts[{index}]"
        if not isinstance(script, dict):
            _issue(issues, "story-ir-panel-script", path, "Each panel script must be an object.")
            continue
        for key in ("panel_id", "beat_id", "panel_role", "action_verb"):
            if not _nonempty(script.get(key)):
                _issue(issues, "story-ir-panel-script", f"{path}.{key}", f"panel_scripts[].{key} is required.")
        role = _nonempty(script.get("panel_role"))
        if role and role not in ALLOWED_PANEL_ROLES:
            _issue(issues, "story-ir-panel-script", f"{path}.panel_role", f"Unsupported panel_role `{role}`.")
        beat_id = _nonempty(script.get("beat_id"))
        if beat_ids and beat_id and beat_id not in beat_ids:
            _issue(issues, "story-ir-panel-script", f"{path}.beat_id", f"panel script references unknown beat_id `{beat_id}`.")
        _validate_source_ref_list(script.get("source_refs"), source_ids, f"{path}.source_refs", "story-ir-panel-script", issues)


def _validate_source_ref_list(
    refs: object,
    source_ids: set[str],
    path: str,
    code: str,
    issues: list[dict[str, str]],
) -> None:
    if not _has_nonempty_string_list(refs):
        _issue(issues, code, path, "source_refs must contain at least one source chunk id.")
        return
    if not source_ids:
        return
    unknown = sorted({_nonempty(ref) for ref in refs if _nonempty(ref)} - source_ids)  # type: ignore[union-attr]
    if unknown:
        _issue(issues, code, path, f"source_refs include unknown chunk ids: {unknown}.")


def _validate_balloon_budget(value: object, panel_path: str, issues: list[dict[str, str]]) -> tuple[bool, bool]:
    if not isinstance(value, dict):
        _issue(issues, "panel-balloon-budget", f"{panel_path}.balloon_budget", "Each panel needs balloon_budget with max_chars and actual_chars.")
        return False, False
    max_chars = value.get("max_chars")
    actual_chars = value.get("actual_chars")
    if not isinstance(max_chars, int) or max_chars <= 0:
        _issue(issues, "panel-balloon-budget", f"{panel_path}.balloon_budget.max_chars", "balloon_budget.max_chars must be a positive integer.")
        return False, False
    if not isinstance(actual_chars, int) or actual_chars < 0:
        _issue(issues, "panel-balloon-budget", f"{panel_path}.balloon_budget.actual_chars", "balloon_budget.actual_chars must be a non-negative integer.")
        return False, False
    if actual_chars > max_chars:
        _issue(issues, "balloon-overflow", f"{panel_path}.balloon_budget", f"Panel text uses {actual_chars} chars but budget is {max_chars}.")
        return False, True
    return True, False


def _validate_reading_order_value(value: object, panel_path: str, issues: list[dict[str, str]]) -> int | None:
    if not isinstance(value, int) or value <= 0:
        _issue(issues, "reading-order", f"{panel_path}.reading_order", "Each panel needs a positive integer reading_order.")
        return None
    return value


def _validate_reading_order_sequence(reading_orders: list[int], panel_count: int, issues: list[dict[str, str]]) -> bool:
    if not panel_count:
        return False
    expected = list(range(1, panel_count + 1))
    passed = len(reading_orders) == panel_count and sorted(reading_orders) == expected
    if not passed:
        _issue(
            issues,
            "reading-order",
            "story/episode-001.json.scenes[].panels[].reading_order",
            "reading_order must be unique and sequential across the episode so layout and review tools know the intended path.",
        )
    return passed


def _validate_no_three_same(sequence: list[str], code: str, field: str, issues: list[dict[str, str]]) -> None:
    for index in range(len(sequence) - 2):
        values = sequence[index : index + 3]
        if values[0] and values[0] == values[1] == values[2]:
            _issue(
                issues,
                code,
                f"story/episode-001.json.scenes[].panels[].{field}",
                f"Do not repeat {field} `{values[0]}` three times in a row.",
            )
            return


def _validate_opening_hook(panels: list[dict[str, Any]], issues: list[dict[str, str]]) -> None:
    if not panels:
        return
    first = panels[0]
    path = "story/episode-001.json.scenes[0].panels[0]"
    hook_type = _nonempty(first.get("hook_type"))
    hook_line = _nonempty(first.get("hook_line"))
    if hook_type not in ALLOWED_HOOK_TYPES:
        _issue(issues, "opening-hook-type", f"{path}.hook_type", "First panel must declare hook_type: conflict, mystery, contrast, or stakes.")
    if not hook_line:
        _issue(issues, "opening-hook-line", f"{path}.hook_line", "First panel needs a standalone hook_line.")
    elif len(hook_line) > 20:
        _issue(issues, "opening-hook-line", f"{path}.hook_line", "hook_line must be 20 characters or fewer.")
    if first.get("is_cover_source") is not True:
        _issue(issues, "opening-cover-source", f"{path}.is_cover_source", "First panel must be marked is_cover_source=true so cover generation has an approved source.")


def _validate_llm_gate(llm_gate: dict[str, Any], issues: list[dict[str, str]], root: Path) -> None:
    if llm_gate.get("status") != "approved":
        _issue(
            issues,
            "llm-gate",
            "qa/story-gate-report.json.llm_gate",
            "LLM story gate must be approved before compose-project. Run the independent review, then record it "
            "with the record-story-review command (the only legal write path for this verdict).",
        )
        return
    author = _nonempty(llm_gate.get("author_pass_id"))
    reviewer = _nonempty(llm_gate.get("reviewer_pass_id"))
    if not author or not reviewer or author == reviewer:
        _issue(
            issues,
            "llm-gate-independent-review",
            "qa/story-gate-report.json.llm_gate.reviewer_pass_id",
            "LLM story gate needs independent review: reviewer_pass_id must exist and differ from author_pass_id.",
        )
    # A verdict without a record-story-review provenance stamp — or one whose
    # episode hash no longer matches — is hand-written or stale (audit P0-2).
    from .review_record import RECORD_STORY_TOOL, check_review_provenance

    for problem in check_review_provenance(llm_gate, expected_tool=RECORD_STORY_TOOL, project=root):
        _issue(issues, "llm-gate-provenance", "qa/story-gate-report.json.llm_gate.provenance", problem)
    checks = llm_gate.get("checks")
    if not isinstance(checks, list) or not checks:
        _issue(
            issues,
            "llm-gate-evidence",
            "qa/story-gate-report.json.llm_gate.checks",
            "LLM gate checks must be a non-empty list with structured evidence.",
        )
        return
    # Same per-check discipline as record-story-review, re-applied here so an
    # inherited/hand-edited report cannot carry failed checks under an
    # approved verdict (release audit P0-1: five failed checks were approved).
    from .review_record import REQUIRED_STORY_CHECKS, validate_review_checks

    parsed_checks = [check for check in checks if isinstance(check, dict)]
    if len(parsed_checks) != len(checks):
        _issue(issues, "llm-gate-evidence", "qa/story-gate-report.json.llm_gate.checks", "Each LLM gate check must be an object.")
    for problem in validate_review_checks(parsed_checks, required_names=REQUIRED_STORY_CHECKS, require_pass=True):
        _issue(issues, "llm-gate-check", "qa/story-gate-report.json.llm_gate.checks", problem)


def _has_nonempty_string_list(value: object) -> bool:
    return isinstance(value, list) and any(_nonempty(item) for item in value)


def _grounding_mode_counts(panels: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for panel in panels:
        grounding = panel.get("grounding")
        if isinstance(grounding, dict):
            mode = _nonempty(grounding.get("type") or grounding.get("mode"))
        else:
            mode = "legacy_life_scene" if _nonempty(panel.get("life_scene")) else ""
        if mode:
            counts[mode] = counts.get(mode, 0) + 1
    return counts


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [_nonempty(item) for item in value if _nonempty(item)]
    text = _nonempty(value)
    return [text] if text else []


def _references_text(left: object, right: object) -> bool:
    left_text = _nonempty(left)
    right_text = _nonempty(right)
    if not left_text or not right_text:
        return False
    if right_text in left_text or left_text in right_text:
        return True
    left_tokens = _semantic_tokens(left_text)
    right_tokens = _semantic_tokens(right_text)
    if left_tokens and right_tokens and left_tokens & right_tokens:
        return True
    for size in (6, 5, 4):
        chunks = {right_text[index : index + size] for index in range(max(0, len(right_text) - size + 1))}
        if any(chunk and chunk in left_text for chunk in chunks):
            return True
    return False


def _semantic_tokens(text: str) -> set[str]:
    tokens = set(re.findall(r"[a-zA-Z0-9_-]{3,}", text.lower()))
    tokens.update(re.findall(r"[\u4e00-\u9fff]{2,}", text))
    stop = {"一个", "这一", "所以", "因为", "不是", "继续", "变成", "需要", "没有", "自己"}
    return {token for token in tokens if token not in stop and len(token) >= 2}


def _substantive_unremovable_reason(value: object) -> bool:
    text = _nonempty(value)
    if len(text) < 18:
        return False
    generic = ("补充说明", "承接", "过渡", "展示概念", "说明概念", "丰富画面", "增加节奏")
    if any(item in text for item in generic):
        return False
    return any(item in text for item in ("删掉", "删除", "没有", "无法", "断", "失去", "break", "remove"))


def _substantive_text(value: object) -> bool:
    return len(_nonempty(value)) >= 8


def _token_signature(value: object) -> str:
    if isinstance(value, list):
        return ",".join(sorted(_nonempty(item) for item in value if _nonempty(item)))
    return "|".join(sorted(_semantic_tokens(_nonempty(value)))) or _nonempty(value)


def _panel_path(scene_index: int, panel_index: int, field: str) -> str:
    return f"story/episode-001.json.scenes[{scene_index}].panels[{panel_index}].{field}"


def _issue(issues: list[dict[str, str]], code: str, path: str, message: str) -> None:
    issues.append({"code": code, "path": path, "message": message})


def _style_name_blocklist() -> set[str]:
    """Art-style display names that must never leak into reader-facing titles.

    When the project folder is named e.g. `mulan-...-deco-chiaroscuro`, the host
    tends to copy the style tag into episode_title as `第一章：织机停声（装饰黑金明暗）`,
    which then prints on the cover and page header. Titles must name the work,
    not the render style.
    """
    names: set[str] = {"装饰黑金明暗"}  # legacy display name (renamed 装饰华光明暗 2026-07-09); old projects may still carry it
    try:
        from .art_style import load_flat_styles

        for entry in load_flat_styles().values():
            name = str(entry.get("display_name") or "").strip()
            if name:
                names.add(name)
    except Exception:  # noqa: BLE001 - a style-registry hiccup must not break the story gate
        pass
    return names


def _check_titles_clean(
    episode: dict[str, Any],
    project_data: dict[str, Any],
    issues: list[dict[str, str]],
) -> None:
    blocklist = _style_name_blocklist()
    targets = [
        ("episode_title", str(episode.get("episode_title") or "")),
        ("book_title", str(episode.get("book_title") or "")),
        ("project_title", str(project_data.get("project_title") or "")),
    ]
    for field_name, value in targets:
        if not value:
            continue
        for style_name in blocklist:
            if style_name and style_name in value:
                _issue(
                    issues,
                    "style-name-in-title",
                    f"story/episode-001.json.{field_name}",
                    f"{field_name} contains the render-style name '{style_name}': {value!r}. "
                    "Titles must name the work/chapter only — never the art style or project-folder tag.",
                )
                break


def _check_mass_traffic_style(
    root: Path,
    episode: dict[str, Any],
    delivery_intent: str,
    issues: list[dict[str, str]],
) -> None:
    """General 讨喜 backstop: mass_traffic must not silently ship a low-reach lane.

    The low-reach set is DERIVED from presets/market_style_preferences.json
    (styles ranked tier B everywhere they appear), not hardcoded — same
    principle as the substyle preference rule, enforced at the top-style
    level. Field report v5.13.3: 桃花源记 straddles two legitimate readings
    (古中国彩色国漫 / 黑白文学墨线) and the per-run tie-break shipped
    monochrome ink-sketch on a mass-traffic delivery. Advisory SKILL prose
    cannot hold this for third-party users; the gate can. An explicit USER
    choice recorded via set-art-style (custom_art_style in
    planning/visual_identity.json) passes — the override then controls the
    look anyway, so the structural style_id is no longer what readers see.
    """
    if delivery_intent != "mass_traffic":
        return
    from .styles import list_showcase_style_ids, low_reach_style_ids

    avoid_ids = low_reach_style_ids()
    style_id = _nonempty(episode.get("style_id"))
    if style_id not in avoid_ids:
        return
    visual_identity = _read_optional_json(root / "planning" / "visual_identity.json")
    if _nonempty(visual_identity.get("custom_art_style")):
        return
    mass_lanes = ", ".join(s for s in list_showcase_style_ids() if s not in avoid_ids)
    _issue(
        issues,
        "style-mass-traffic",
        "story/episode-001.json.style_id",
        f"style_id={style_id} is a low-reach lane (market preference tier B) and delivery_intent=mass_traffic. "
        f"Pick a broad-appeal style ({mass_lanes}), or — if the USER explicitly asked for this look — "
        "record that choice with set-art-style (writes custom_art_style) and re-run.",
    )


def _nonempty(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
