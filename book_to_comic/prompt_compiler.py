from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import PanelArtSpec, StyleSpec
from .styles import get_style
from .narrative_identity import narrative_identity_summary
from .visual_identity import visual_identity_summary


def compile_character_reference(
    style: StyleSpec | str,
    characters: Mapping[str, str],
    variant_id: str | None = None,
    visual_identity: Mapping[str, Any] | None = None,
) -> str:
    spec = _style(style)
    lines = [
        _style_header(spec, variant_id, visual_identity),
        "Task: create a character reference sheet for recurring comic characters.",
        *visual_identity_lock_lines(visual_identity=visual_identity),
        *world_model_lock_lines(visual_identity=visual_identity),
        "Use neutral background, stable lighting, full-body front and 3/4 poses, expression samples and hand samples.",
        "Do not draw speech bubbles, captions, labels, readable text, letters, numbers or pseudo-text.",
        "Characters:",
    ]
    lines.extend(f"- {key}: {value}" for key, value in characters.items())
    lines.extend(_style_blocks(spec, ("style_core", "character")))
    lines.extend(_avoid_lines(spec))
    return "\n".join(lines).strip() + "\n"


def compile_environment_reference(
    style: StyleSpec | str,
    environment_id: str,
    environment: str,
    variant_id: str | None = None,
    visual_identity: Mapping[str, Any] | None = None,
) -> str:
    spec = _style(style)
    lines = [
        _style_header(spec, variant_id, visual_identity),
        f"Task: create a recurring environment reference sheet for {environment_id}.",
        *visual_identity_lock_lines(visual_identity=visual_identity),
        *world_model_lock_lines(visual_identity=visual_identity),
        f"Environment: {environment}",
        "Show layout anchors, light source, materials, foreground/midground/background, and reusable camera angles.",
        "Do not include readable text, labels, signage, UI text or pseudo-text.",
    ]
    lines.extend(_style_blocks(spec, ("style_core", "environment", "camera")))
    lines.extend(_avoid_lines(spec))
    return "\n".join(lines).strip() + "\n"


def compile_prop_reference(
    style: StyleSpec | str,
    prop_id: str,
    prop: str,
    variant_id: str | None = None,
    visual_identity: Mapping[str, Any] | None = None,
) -> str:
    spec = _style(style)
    lines = [
        _style_header(spec, variant_id, visual_identity),
        f"Task: create a key prop reference for {prop_id}.",
        *visual_identity_lock_lines(visual_identity=visual_identity),
        *world_model_lock_lines(visual_identity=visual_identity),
        f"Prop: {prop}",
        "Show silhouette, material, scale, hand interaction, and possible state changes.",
        "No readable text, labels, numbers or pseudo-text.",
    ]
    lines.extend(_style_blocks(spec, ("style_core", "character")))
    lines.extend(_avoid_lines(spec))
    return "\n".join(lines).strip() + "\n"


def compile_panel_prompt(
    style: StyleSpec | str,
    panel: PanelArtSpec,
    characters: Mapping[str, str],
    environments: Mapping[str, str],
    props: Mapping[str, str],
    variant_id: str | None = None,
    reference_pack: Mapping[str, Any] | None = None,
    visual_identity: Mapping[str, Any] | None = None,
) -> str:
    spec = _style(style)
    panel_lock = _panel_lock(reference_pack, panel.panel_id)
    locked_characters = _lock_characters(panel_lock) or list(panel.characters_present)
    environment_id = str(panel_lock.get("environment_id") or panel.environment_id) if panel_lock else panel.environment_id
    props_and_states = _lock_props(panel_lock) or panel.props_and_states
    active_characters = {
        key: _character_text(key, characters, reference_pack, panel_lock)
        for key in locked_characters
        if _character_text(key, characters, reference_pack, panel_lock)
    }
    active_props = {
        key: _prop_text(key, props, reference_pack)
        for key in props_and_states
        if _prop_text(key, props, reference_pack)
    }
    lines = [
        _style_header(spec, variant_id, visual_identity),
        f"Task: generate finished comic panel {panel.panel_id}.",
        *visual_identity_lock_lines(reference_pack=reference_pack, visual_identity=visual_identity),
        *world_model_lock_lines(reference_pack=reference_pack, visual_identity=visual_identity),
        "Use approved character, environment and prop references when available; do not redesign locked elements.",
        "Only include the characters listed for this panel.",
        f"Characters present: {', '.join(locked_characters) or 'none'}",
    ]
    lines.extend(reference_pack_panel_lock_lines(panel.panel_id, reference_pack))
    lines.extend(f"- {key}: {value}" for key, value in active_characters.items())
    lines.extend(
        [
            f"Environment {environment_id}: {_environment_text(environment_id, environments, reference_pack)}",
            f"Time: {panel.time}",
            f"Shot: {panel.shot_size}; camera: {panel.camera_angle}; lens feel: {panel.lens_feel}",
            f"Focal point: {panel.focal_point}",
            f"Foreground: {panel.foreground}",
            f"Midground: {panel.midground}",
            f"Background: {panel.background}",
            f"Action: {panel.action}",
            f"Emotion: {panel.emotion}",
            f"Eyeline: {panel.eyeline}",
        ]
    )
    if active_props:
        lines.append("Props in this panel:")
        for prop_id, prop in active_props.items():
            lines.append(f"- {prop_id}: {prop}; state: {props_and_states.get(prop_id, '')}")
    lines.extend(
        [
            f"Continuity from: {_lock_continuity(panel_lock) or panel.continuity_from or 'start of episode'}",
            f"Transition to next: {panel.transition_to_next or 'episode close'}",
            f"Lettering safe zone: {_lock_lettering_safe_zone(panel_lock) or panel.lettering_safe_zone}",
            f"Aspect ratio: {panel.aspect_ratio}",
        ]
    )
    # When a custom_art_style OVERRIDE is set it owns medium/line/color/finish.
    # The built-in style blocks (style_core, character, avoid...) carry the
    # HOST style's look — "clean digital line, soft gradients, full-color webtoon"
    # — which fights the override and dilutes its signature. Drop the look blocks
    # and keep only composition-level guidance so nothing contradicts the override.
    if _custom_art_style(visual_identity):
        lines.append("Composition only (the ART STYLE OVERRIDE above dictates medium, line, color and finish — ignore any other look/medium cues):")
        lines.extend(_style_blocks(spec, ("environment", "camera")))
    else:
        lines.extend(_style_blocks(spec, ("style_core", "character", "environment", "camera")))
        lines.extend(_avoid_lines(spec))
    lines.extend(
        [
            "Text handling: no readable text, letters, numbers, signage, captions, speech bubbles or pseudo-text inside the generated image.",
            "Full-bleed: the artwork must fill the entire canvas edge to edge — no borders, no frame lines, no mats, no letterboxing or flat margins.",
            "Leave natural negative space for post-production Chinese lettering; do not draw blank text boxes.",
            "Anatomy and space: correct hand structure (five fingers, natural joints), whole bodies attached to visible torsos — no limbs sprouting from doors, walls or frames; props (scrolls, tools, weapons) held with a plausible grip and correct occlusion, not floating or passing through solid objects; keep foreground/subject/background depth physically coherent.",
        ]
    )
    return "\n".join(line for line in lines if line).strip() + "\n"


def reference_pack_panel_lock_lines(panel_id: str, reference_pack: Mapping[str, Any] | None) -> list[str]:
    lock = _panel_lock(reference_pack, panel_id)
    if not lock:
        return []
    lines = ["Visual contract lock:"]
    characters = _lock_characters(lock)
    if characters:
        lines.append(f"- locked characters: {', '.join(characters)}")
    wardrobe_state = lock.get("wardrobe_state")
    if isinstance(wardrobe_state, Mapping) and wardrobe_state:
        wardrobe = "; ".join(f"{key}: {value}" for key, value in wardrobe_state.items() if str(value).strip())
        if wardrobe:
            lines.append(f"- wardrobe_state: {wardrobe}")
    environment_id = str(lock.get("environment_id", "")).strip()
    if environment_id:
        environment = _reference_environment(environment_id, reference_pack)
        lines.append(f"- environment_id: {environment_id}" + (f"; {environment}" if environment else ""))
    props_and_states = _lock_props(lock)
    if props_and_states:
        prop_text = "; ".join(f"{key}: {value}" for key, value in props_and_states.items())
        lines.append(f"- props_and_states: {prop_text}")
    continuity = _lock_continuity(lock)
    if continuity:
        lines.append(f"- continuity_from_prev: {continuity}")
    safe_zone = _lock_lettering_safe_zone(lock)
    if safe_zone:
        lines.append(f"- lettering_safe_zone: {safe_zone}")
    return lines


def visual_identity_lock_lines(
    reference_pack: Mapping[str, Any] | None = None,
    visual_identity: Mapping[str, Any] | None = None,
) -> list[str]:
    summary: Mapping[str, Any] | None = None
    if isinstance(reference_pack, Mapping):
        value = reference_pack.get("visual_identity_summary")
        if isinstance(value, Mapping):
            summary = value
    if summary is None and isinstance(visual_identity, Mapping):
        summary = visual_identity_summary(visual_identity)
    if not isinstance(summary, Mapping) or not any(str(value).strip() for value in summary.values()):
        return []
    return [
        "Project visual identity lock:",
        f"- Book-specific adaptation form: {_identity_text(summary.get('adaptation_form'))}",
        f"- Cast model: {_identity_text(summary.get('cast_model'))}",
        f"- Character shape language: {_identity_text(summary.get('character_shape_language'))}",
        f"- Era and geography: {_identity_text(summary.get('era_geography'))}",
        f"- Environment language: {_identity_text(summary.get('environment_language'))}",
        f"- Signature motifs: {_identity_text(summary.get('signature_motifs'))}",
        f"- Palette and lighting: {_identity_text(summary.get('palette_lighting'))}",
        f"- Camera and composition: {_identity_text(summary.get('camera_composition'))}",
        f"- Forbidden carry-over from prior projects: {_identity_text(summary.get('forbidden_carryover'))}",
    ]


def world_model_lock_lines(
    reference_pack: Mapping[str, Any] | None = None,
    visual_identity: Mapping[str, Any] | None = None,
) -> list[str]:
    summary: Mapping[str, Any] | None = None
    if isinstance(reference_pack, Mapping):
        value = reference_pack.get("world_model_summary")
        if isinstance(value, Mapping):
            summary = value
    if summary is None and isinstance(visual_identity, Mapping):
        value = visual_identity.get("world_model_summary")
        if isinstance(value, Mapping):
            summary = value
    if not isinstance(summary, Mapping) or not any(str(value).strip() for value in summary.values()):
        return []
    return [
        "World model lock:",
        f"- Era: {_identity_text(summary.get('era'))}",
        f"- Geography: {_identity_text(summary.get('geography'))}",
        f"- Institutions: {_identity_text(summary.get('institutions'))}",
        f"- Material culture: {_identity_text(summary.get('material_culture'))}",
        f"- Access rules: {_identity_text(summary.get('access_rules'))}",
    ]


def narrative_identity_lock_lines(narrative_identity: Mapping[str, Any] | None = None) -> list[str]:
    if not isinstance(narrative_identity, Mapping):
        return []
    summary = narrative_identity_summary(narrative_identity)
    if not any(str(value).strip() for value in summary.values()):
        return []
    return [
        "Project narrative identity lock:",
        f"- Book-specific voice: {_identity_text(summary.get('narrative_voice'))}",
        f"- Why this voice belongs to this book: {_identity_text(summary.get('why_specific_to_this_book'))}",
        f"- Reader bridge policy: {_identity_text(summary.get('reader_bridge_policy'))}",
        f"- Tone matrix: {_identity_text(summary.get('tone_matrix'))}",
        f"- Speaker registers: {_identity_text(summary.get('speaker_registers'))}",
        f"- Panel text policy: {_identity_text(summary.get('panel_text_policy'))}",
        f"- Forbidden generic phrases: {_identity_text(summary.get('forbidden_generic_phrases'))}",
        f"- Forbidden cross-book phrases: {_identity_text(summary.get('forbidden_cross_book_phrases'))}",
    ]


def compile_repair_prompt(
    style: StyleSpec | str,
    panel_id: str,
    qa_failures: list[str] | tuple[str, ...],
) -> str:
    spec = _style(style)
    lines = [
        f"Repair panel {panel_id} in {spec.short_name}.",
        "Keep the approved composition and identity locks; fix only the failed items.",
        "Failures:",
    ]
    lines.extend(f"- {item}" for item in qa_failures)
    lines.extend(
        [
            "Maintain the same style signature:",
            *[f"- {item}" for item in spec.qa.get("signature", ())[:4]],
            "No readable text or pseudo-text.",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _style(style: StyleSpec | str) -> StyleSpec:
    return get_style(style) if isinstance(style, str) else style


def _style_header(
    style: StyleSpec,
    variant_id: str | None,
    visual_identity: Mapping[str, Any] | None = None,
) -> str:
    variant = variant_id or (style.selection.get("variants", ("default",))[0] if style.selection.get("variants") else "default")
    base = f"Style: {style.name} ({style.short_name}); variant={variant}"
    custom = _custom_art_style(visual_identity)
    if custom:
        return (
            f"ART STYLE OVERRIDE (user-specified, ABSOLUTE highest priority): {custom}\n"
            "This override ALONE controls medium, line, color, texture and finish. It supersedes every other "
            "style, palette, lighting or medium cue anywhere below — if any later line suggests a different look "
            "(webtoon, clean digital line, soft gradients, a named palette, etc.), IGNORE it and follow only this "
            "override. Everything below is for shot, composition, character/prop identity and panel structure only.\n"
            # Compiler-level IP line, not just a SKILL rule (release audit
            # P1-10): whatever text reached custom_art_style, the prompt still
            # forbids replicating existing works' character designs.
            "Original design only: do NOT replicate character designs, logos or trade dress from any existing "
            "film/game/comic/artist portfolio — treat the override as technique (medium, line, color strategy, "
            "face geometry), never as an instruction to copy a specific creator's work.\n"
            f"{base}"
        )
    return base


def _custom_art_style(visual_identity: Mapping[str, Any] | None) -> str:
    if not isinstance(visual_identity, Mapping):
        return ""
    return str(visual_identity.get("custom_art_style", "")).strip()


def _style_blocks(style: StyleSpec, block_names: tuple[str, ...]) -> list[str]:
    lines: list[str] = []
    for block_name in block_names:
        lines.append(f"{block_name}:")
        lines.extend(f"- {item}" for item in style.prompt_blocks.get(block_name, ()))
    return lines


def _avoid_lines(style: StyleSpec) -> list[str]:
    lines = ["avoid:"]
    lines.extend(f"- {item}" for item in style.prompt_blocks.get("avoid", ()))
    return lines


def _identity_text(value: object) -> str:
    if isinstance(value, Mapping):
        parts: list[str] = []
        for key in sorted(value):
            text = _identity_text(value[key])
            if text:
                parts.append(f"{key}: {text}")
        return "; ".join(parts)
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "").strip()


def _panel_lock(reference_pack: Mapping[str, Any] | None, panel_id: str) -> dict[str, Any]:
    if not isinstance(reference_pack, Mapping):
        return {}
    panel_locks = reference_pack.get("panel_locks")
    if not isinstance(panel_locks, Mapping):
        return {}
    lock = panel_locks.get(panel_id)
    return dict(lock) if isinstance(lock, Mapping) else {}


def _lock_characters(panel_lock: Mapping[str, Any]) -> list[str]:
    value = panel_lock.get("characters_present") if panel_lock else None
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _lock_props(panel_lock: Mapping[str, Any]) -> dict[str, str]:
    value = panel_lock.get("props_and_states") if panel_lock else None
    if not isinstance(value, Mapping):
        return {}
    return {str(key): str(item) for key, item in value.items() if str(key).strip()}


def _lock_continuity(panel_lock: Mapping[str, Any]) -> str:
    if not panel_lock:
        return ""
    return str(panel_lock.get("continuity_from_prev") or panel_lock.get("continuity_from") or "").strip()


def _lock_lettering_safe_zone(panel_lock: Mapping[str, Any]) -> str:
    if not panel_lock:
        return ""
    return str(panel_lock.get("lettering_safe_zone") or "").strip()


def _character_text(
    character_id: str,
    characters: Mapping[str, str],
    reference_pack: Mapping[str, Any] | None,
    panel_lock: Mapping[str, Any],
) -> str:
    parts: list[str] = []
    entry = _reference_entry(reference_pack, "characters", character_id)
    if entry:
        for key in ("prompt_fragment", "visual", "name", "role"):
            value = str(entry.get(key, "")).strip()
            if value and value not in parts:
                parts.append(value)
        wardrobe_lock = str(entry.get("wardrobe_lock", "")).strip()
        if wardrobe_lock:
            parts.append(f"wardrobe_lock: {wardrobe_lock}")
    if character_id in characters and characters[character_id] not in parts:
        parts.append(characters[character_id])
    wardrobe_state = panel_lock.get("wardrobe_state") if panel_lock else None
    if isinstance(wardrobe_state, Mapping):
        locked = str(wardrobe_state.get(character_id, "")).strip()
        if locked:
            parts.append(f"panel wardrobe: {locked}")
    return "; ".join(parts)


def _environment_text(
    environment_id: str,
    environments: Mapping[str, str],
    reference_pack: Mapping[str, Any] | None,
) -> str:
    parts: list[str] = []
    reference = _reference_environment(environment_id, reference_pack)
    if reference:
        parts.append(reference)
    fallback = environments.get(environment_id, "")
    if fallback and fallback not in parts:
        parts.append(fallback)
    return "; ".join(parts)


def _reference_environment(environment_id: str, reference_pack: Mapping[str, Any] | None) -> str:
    entry = _reference_entry(reference_pack, "environments", environment_id)
    if not entry:
        return ""
    parts = []
    for key in ("name", "kind"):
        value = str(entry.get(key, "")).strip()
        if value:
            parts.append(value)
    anchors = entry.get("anchors")
    if isinstance(anchors, list) and anchors:
        parts.append("anchors: " + ", ".join(str(anchor) for anchor in anchors if str(anchor).strip()))
    return "; ".join(parts)


def _prop_text(prop_id: str, props: Mapping[str, str], reference_pack: Mapping[str, Any] | None) -> str:
    parts: list[str] = []
    entry = _reference_entry(reference_pack, "props", prop_id)
    if entry:
        for key in ("description", "first_state"):
            value = str(entry.get(key, "")).strip()
            if value and value not in parts:
                parts.append(value)
    fallback = props.get(prop_id, "")
    if fallback and fallback not in parts:
        parts.append(fallback)
    return "; ".join(parts)


def _reference_entry(reference_pack: Mapping[str, Any] | None, section: str, key: str) -> dict[str, Any]:
    if not isinstance(reference_pack, Mapping):
        return {}
    entries = reference_pack.get(section)
    if not isinstance(entries, Mapping):
        return {}
    value = entries.get(key)
    return dict(value) if isinstance(value, Mapping) else {}
