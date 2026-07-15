from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from .models import ArtBrief, StyleSelectionResult, StyleSpec


_BASE_DIR = Path(__file__).resolve().parent
_PRESET_PATH = _BASE_DIR / "presets" / "nine_styles.json"
_MATRIX_PATH = _BASE_DIR / "presets" / "style_selection_matrix.json"
_MARKET_PREF_PATH = _BASE_DIR / "presets" / "market_style_preferences.json"

_SHOWCASE_STYLE_IDS = (
    "manga",
    "webtoon-manhwa",
    "manhua",
    "franco-belgian-bd",
    "editorial",
    "comic-strip",
    "doodle",
    "retro-halftone",
    "ink-sketch",
)

def low_reach_style_ids() -> tuple[str, ...]:
    """Styles whose market lanes are ALL low-reach — derived, not hardcoded.

    General 讨喜 rule, same principle as the substyle preference table: a
    mass_traffic delivery keeps to broad-appeal lanes by default. "Low-reach"
    is read from presets/market_style_preferences.json — a style counts only
    when every lane it appears in is tier B (today that computes to
    ink-sketch, whose own market_note says "less mass-market"). Styles the
    table ranks S/A anywhere, or doesn't rank at all, are never demoted.
    All lanes stay fully available for hardcore_showcase, and for
    mass_traffic when the USER names the look (set-art-style records that
    choice as custom_art_style, which bypasses selection and satisfies the
    story-gate check).
    """
    entries = _read_json(_MARKET_PREF_PATH).get("preferred_variants", [])
    tiers: dict[str, set[str]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        style_id = str(entry.get("style_id") or "").strip()
        if style_id:
            tiers.setdefault(style_id, set()).add(str(entry.get("tier") or "").strip())
    return tuple(sorted(style_id for style_id, seen in tiers.items() if seen and seen <= {"B"}))

_ROOT_KEYS = {"schema_version", "stable_style_ids", "compatibility_aliases", "styles"}
_STYLE_KEYS = {
    "display_name",
    "short_name",
    "taxonomy",
    "selection",
    "art_direction",
    "prompt_blocks",
    "qa",
    "substyles",
    "sources",
    "balloon_style",
}
_TAXONOMY_KEYS = {"tradition", "format", "medium", "note"}
_SELECTION_KEYS = {"best_for", "avoid_for", "variants", "platforms"}
_PROMPT_BLOCK_KEYS = {"style_core", "character", "environment", "camera", "avoid"}
_QA_KEYS = {"signature", "hard_fail"}
_SUBSTYLE_KEYS = {
    "id",
    "label",
    "use_when",
    "avoid_when",
    "visual_traits",
    "prompt_additions",
    "qa_focus",
    "sources",
}


def list_showcase_style_ids() -> tuple[str, ...]:
    return _SHOWCASE_STYLE_IDS


def list_style_ids() -> tuple[str, ...]:
    data = _registry()
    return tuple(data["stable_style_ids"]) + tuple(data["compatibility_aliases"].keys())


def balloon_style_for(style_id: str) -> dict[str, Any]:
    """Raw balloon_style parameters of a top-level style (empty dict when absent
    or the style is unknown — callers fall back to renderer defaults)."""
    data = _registry()
    canonical_id = data["compatibility_aliases"].get(style_id, style_id)
    style_data = data["styles"].get(canonical_id)
    if not isinstance(style_data, dict):
        return {}
    value = style_data.get("balloon_style")
    return dict(value) if isinstance(value, dict) else {}


def get_style(style_id: str) -> StyleSpec:
    data = _registry()
    canonical_id = data["compatibility_aliases"].get(style_id, style_id)
    try:
        style_data = data["styles"][canonical_id]
    except KeyError as exc:
        known = ", ".join(list_style_ids())
        raise ValueError(f"Unknown style '{style_id}'. Known styles: {known}") from exc
    return _style_from_data(canonical_id, data["schema_version"], style_data)


def iter_styles(include_aliases: bool = False) -> tuple[StyleSpec, ...]:
    styles = tuple(get_style(style_id) for style_id in _SHOWCASE_STYLE_IDS)
    if not include_aliases:
        return styles
    return styles + tuple(get_style(alias) for alias in _registry()["compatibility_aliases"])


def choose_random_style(seed: int | None = None) -> StyleSpec:
    rng = random.Random(seed)
    return get_style(rng.choice(_SHOWCASE_STYLE_IDS))


def choose_style_for_brief(
    brief: ArtBrief | dict[str, object],
    *,
    delivery_intent: str | None = None,
) -> StyleSelectionResult:
    normalized = _brief_axes(brief)
    hard = _hard_rule_style(normalized, brief)
    matrix = _read_json(_MATRIX_PATH)
    scores: dict[str, float] = {}
    variants: dict[str, str] = {}
    market_boosts: dict[str, float] = {}
    for style_id, style_scores in matrix["scores"].items():
        scores[style_id] = sum(float(style_scores[axis]) * normalized[axis] for axis in matrix["axes"])
        style = get_style(style_id)
        variant_id = _choose_variant_for_brief(style_id, style.selection.get("variants", ()), normalized, brief)
        variants[style_id] = variant_id
        market_boosts[style_id] = _market_preference_boost(style_id, variant_id, normalized, brief)
        scores[style_id] += market_boosts[style_id]
    if hard:
        scores[hard] += 25.0
    ranker = lambda item: (-scores[item], _SHOWCASE_STYLE_IDS.index(item))  # noqa: E731
    natural_winner = sorted(scores, key=ranker)[0]
    demoted = False
    if delivery_intent == "mass_traffic":
        # General 讨喜 rule at the top-style level (the substyle table already
        # does this within a style): a mass-traffic delivery must not land on
        # a low-reach lane just because the content axes straddle two
        # legitimate readings — 桃花源记 reads as both 古中国彩色国漫 and
        # 黑白文学墨线, and the per-run tie-break once shipped monochrome to a
        # mass audience. Structural demotion (below every other candidate,
        # hard rule included), not a calibrated penalty: only an explicit
        # USER choice (set-art-style, which bypasses selection entirely) may
        # put a low-reach style on a mass-traffic delivery.
        avoid_ids = low_reach_style_ids()
        floor = min(scores.values()) - 1.0
        for avoid_id in avoid_ids:
            if avoid_id in scores:
                scores[avoid_id] = min(scores[avoid_id], floor)
        demoted = natural_winner in avoid_ids
    style_id = sorted(scores, key=ranker)[0]
    variant_id = variants[style_id]
    reason_parts = []
    if hard == style_id:
        reason_parts.append("hard-rule")
    if market_boosts.get(style_id, 0.0) > 0:
        reason_parts.append("market-preferred")
    if demoted:
        reason_parts.append("mass-traffic-demotion")
    if not reason_parts:
        reason_parts.append("weighted-style-selection")
    reason = "+".join(reason_parts)
    return StyleSelectionResult(style_id=style_id, variant_id=variant_id, score=round(scores[style_id], 3), reason=reason)


def choose_variant_for_style(style_id: str, brief: ArtBrief | dict[str, object]) -> StyleSelectionResult:
    style = get_style(style_id)
    normalized = _brief_axes(brief)
    variant_id = _choose_variant_for_brief(style.id, style.selection.get("variants", ()), normalized, brief)
    market_boost = _market_preference_boost(style.id, variant_id, normalized, brief)
    reason_parts = ["fixed-style"]
    if market_boost > 0:
        reason_parts.append("market-preferred")
    else:
        reason_parts.append("content-fit")
    return StyleSelectionResult(
        style_id=style.id,
        variant_id=variant_id,
        score=round(market_boost, 3),
        reason="+".join(reason_parts),
    )


def style_show(style_id: str) -> str:
    style = get_style(style_id)
    lines = [
        f"id: {style.id}",
        f"name: {style.name}",
        f"short_name: {style.short_name}",
        f"reference: {style.reference}",
        f"best_for: {', '.join(style.selection.get('best_for', ())) }",
        f"variants: {', '.join(style.selection.get('variants', ())) }",
        "signature:",
    ]
    lines.extend(f"- {item}" for item in style.qa.get("signature", ()))
    lines.append("hard_fail:")
    lines.extend(f"- {item}" for item in style.qa.get("hard_fail", ()))
    lines.append("prompt_core:")
    lines.extend(f"- {item}" for item in style.prompt_blocks.get("style_core", ()))
    lines.append("substyles:")
    lines.extend(f"- {item['id']}: {item['label']}" for item in style.substyles)
    lines.append("avoid:")
    lines.extend(f"- {item}" for item in style.prompt_blocks.get("avoid", ()))
    return "\n".join(lines).strip() + "\n"


def load_style_registry(path: str | Path | None = None) -> dict[str, Any]:
    data = _read_json(Path(path) if path else _PRESET_PATH)
    validate_style_registry(data)
    return data


def validate_style_registry(data: dict[str, Any]) -> None:
    _ensure_keys(data, _ROOT_KEYS, "style registry")
    stable_ids = data["stable_style_ids"]
    if tuple(stable_ids) != _SHOWCASE_STYLE_IDS:
        raise ValueError("stable_style_ids must match the nine supported style IDs in order")
    if not isinstance(data["compatibility_aliases"], dict):
        raise ValueError("compatibility_aliases must be an object")
    if set(data["styles"].keys()) != set(_SHOWCASE_STYLE_IDS):
        raise ValueError("styles must contain exactly the nine supported style IDs")
    for style_id, style_data in data["styles"].items():
        _validate_style(style_id, style_data)


def _registry() -> dict[str, Any]:
    global _CACHED_REGISTRY
    try:
        return _CACHED_REGISTRY
    except NameError:
        _CACHED_REGISTRY = load_style_registry()
        return _CACHED_REGISTRY


def _market_preferences() -> dict[str, Any]:
    global _CACHED_MARKET_PREFERENCES
    try:
        return _CACHED_MARKET_PREFERENCES
    except NameError:
        _CACHED_MARKET_PREFERENCES = _read_json(_MARKET_PREF_PATH)
        return _CACHED_MARKET_PREFERENCES


def _validate_style(style_id: str, style_data: dict[str, Any]) -> None:
    _ensure_keys(style_data, _STYLE_KEYS, f"style {style_id}", unknown_prefix="Unknown style field")
    _ensure_keys(style_data["taxonomy"], _TAXONOMY_KEYS, f"style {style_id}.taxonomy")
    _ensure_keys(style_data["selection"], _SELECTION_KEYS, f"style {style_id}.selection")
    _ensure_keys(style_data["prompt_blocks"], _PROMPT_BLOCK_KEYS, f"style {style_id}.prompt_blocks")
    _ensure_keys(style_data["qa"], _QA_KEYS, f"style {style_id}.qa")
    for key in ("display_name", "short_name"):
        if not isinstance(style_data[key], str) or not style_data[key].strip():
            raise ValueError(f"style {style_id}.{key} must be a non-empty string")
    for label, value in (
        ("selection.best_for", style_data["selection"]["best_for"]),
        ("selection.avoid_for", style_data["selection"]["avoid_for"]),
        ("selection.variants", style_data["selection"]["variants"]),
        ("selection.platforms", style_data["selection"]["platforms"]),
        ("qa.signature", style_data["qa"]["signature"]),
        ("qa.hard_fail", style_data["qa"]["hard_fail"]),
        ("sources", style_data["sources"]),
    ):
        _ensure_string_list(value, f"style {style_id}.{label}")
    for block, value in style_data["prompt_blocks"].items():
        _ensure_string_list(value, f"style {style_id}.prompt_blocks.{block}")
    substyle_ids = _validate_substyles(style_id, style_data["substyles"])
    unknown_variants = [variant for variant in style_data["selection"]["variants"] if variant not in substyle_ids]
    if unknown_variants:
        raise ValueError(
            f"style {style_id}.selection.variants must reference substyles: {', '.join(unknown_variants)}"
        )


def _validate_substyles(style_id: str, value: object) -> set[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"style {style_id}.substyles must be a non-empty list")
    seen: set[str] = set()
    for index, item in enumerate(value):
        label = f"style {style_id}.substyles[{index}]"
        _ensure_keys(item, _SUBSTYLE_KEYS, label)
        substyle_id = item["id"]
        if not isinstance(substyle_id, str) or not substyle_id.strip():
            raise ValueError(f"{label}.id must be a non-empty string")
        if substyle_id in seen:
            raise ValueError(f"Duplicate substyle id in style {style_id}: {substyle_id}")
        seen.add(substyle_id)
        for key in ("label", "use_when", "avoid_when"):
            if not isinstance(item[key], str) or not item[key].strip():
                raise ValueError(f"{label}.{key} must be a non-empty string")
        for key in ("visual_traits", "prompt_additions", "qa_focus", "sources"):
            _ensure_string_list(item[key], f"{label}.{key}")
    return seen


def _ensure_keys(
    obj: object,
    allowed: set[str],
    label: str,
    unknown_prefix: str = "Unknown field",
) -> None:
    if not isinstance(obj, dict):
        raise ValueError(f"{label} must be an object")
    keys = set(obj.keys())
    missing = allowed - keys
    if missing:
        raise ValueError(f"{label} missing required field(s): {', '.join(sorted(missing))}")
    unknown = keys - allowed
    if unknown:
        raise ValueError(f"{unknown_prefix} in {label}: {', '.join(sorted(unknown))}")


def _ensure_string_list(value: object, label: str) -> None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a list of strings")


def _style_from_data(style_id: str, schema_version: str, data: dict[str, Any]) -> StyleSpec:
    taxonomy = dict(data["taxonomy"])
    selection = _tuple_values(data["selection"])
    prompt_blocks = {key: tuple(value) for key, value in data["prompt_blocks"].items()}
    qa = {key: tuple(value) for key, value in data["qa"].items()}
    return StyleSpec(
        id=style_id,
        name=data["display_name"],
        reference=f"{taxonomy['tradition']} / {taxonomy['format']} / {taxonomy['medium']}",
        suitable_for="、".join(data["selection"]["best_for"]),
        prompt_spec=_compile_prompt_spec(data),
        schema_version=schema_version,
        short_name=data["short_name"],
        taxonomy=taxonomy,
        selection=selection,
        art_direction=dict(data["art_direction"]),
        prompt_blocks=prompt_blocks,
        qa=qa,
        substyles=tuple(dict(item) for item in data["substyles"]),
        sources=tuple(data["sources"]),
    )


def _compile_prompt_spec(data: dict[str, Any]) -> str:
    blocks = data["prompt_blocks"]
    art = data["art_direction"]
    lines = [
        f"{data['display_name']} ({data['short_name']})",
        f"taxonomy: {data['taxonomy']['tradition']}; {data['taxonomy']['format']}; {data['taxonomy']['medium']}",
        f"style boundary: {data['taxonomy']['note']}",
        "style_core:",
    ]
    lines.extend(f"- {item}" for item in blocks["style_core"])
    for key in ("character", "environment", "camera"):
        lines.append(f"{key}:")
        lines.extend(f"- {item}" for item in blocks[key])
    lines.append("substyles:")
    for substyle in data["substyles"]:
        lines.append(f"- {substyle['id']} ({substyle['label']}): {substyle['use_when']}")
        for addition in substyle["prompt_additions"]:
            lines.append(f"  - {addition}")
    lines.extend(
        [
            "art_direction:",
            f"- line: {art.get('line', '')}",
            f"- color: {art.get('color', '')}",
            f"- lighting: {art.get('lighting', '')}",
            f"- props: {art.get('props', '')}",
            f"- lettering: {art.get('lettering', '')}",
            "avoid:",
        ]
    )
    lines.extend(f"- {item}" for item in blocks["avoid"])
    lines.extend(
        [
            "- readable text, letters, numbers, pseudo-text, captions, labels, speech bubbles",
            "post-production lettering only; reserve natural negative space for later Chinese lettering",
        ]
    )
    return "\n".join(line for line in lines if line).strip()


def _tuple_values(data: dict[str, Any]) -> dict[str, Any]:
    converted: dict[str, Any] = {}
    for key, value in data.items():
        converted[key] = tuple(value) if isinstance(value, list) else value
    return converted


def _market_preference_boost(
    style_id: str,
    variant_id: str,
    axes: dict[str, float],
    brief: ArtBrief | dict[str, object],
) -> float:
    best = 0.0
    for rule in _market_preferences().get("preferred_variants", ()):
        if rule.get("style_id") != style_id or rule.get("variant_id") != variant_id:
            continue
        if _market_rule_matches(rule, axes, brief):
            best = max(best, float(rule.get("boost", 0.0)))
    return best


def _market_rule_matches(rule: dict[str, Any], axes: dict[str, float], brief: ArtBrief | dict[str, object]) -> bool:
    combined = _brief_combined(brief)
    if any(signal in combined for signal in rule.get("avoid_any", ())):
        return False
    min_axes = rule.get("min_axes", {})
    if any(axes.get(axis, 0.0) < float(minimum) for axis, minimum in min_axes.items()):
        return False
    max_axes = rule.get("max_axes", {})
    if any(axes.get(axis, 0.0) > float(maximum) for axis, maximum in max_axes.items()):
        return False
    match_any = rule.get("match_any", ())
    if match_any and not any(signal in combined for signal in match_any):
        return False
    return True


def _choose_variant_for_brief(
    style_id: str,
    variants: object,
    axes: dict[str, float],
    brief: ArtBrief | dict[str, object],
) -> str:
    if not isinstance(variants, tuple) or not variants:
        return "default"

    ordered = tuple(str(variant) for variant in variants)
    available = set(ordered)

    def pick(*candidates: str) -> str:
        for candidate in candidates:
            if candidate in available:
                return candidate
        return ordered[0]

    combined = _brief_combined(brief)

    if style_id == "manga":
        if axes["humor"] >= 4 and axes["plot"] <= 3:
            return pick("yonkoma-gag", "chibi-sd-comic")
        if axes["action"] >= 4:
            return pick("shonen-kinetic", "gekiga-cinematic")
        if "romance" in combined or "young adult" in combined:
            return pick("shojo-romance", "josei-everyday")
        if "literary" in combined or axes["premium_editorial"] >= 4:
            return pick("gekiga-cinematic", "classic-screentone")
        return pick("classic-screentone", "gekiga-cinematic")

    if style_id == "webtoon-manhwa":
        if "romance" in combined and ("fantasy" in combined or axes["historical_world"] >= 4):
            return pick("romance-fantasy", "romance-polished")
        if "romance" in combined or "relationship" in combined or "dating" in combined:
            return pick("romance-polished", "urban-drama")
        if axes["action"] >= 4:
            return pick("action-cinematic", "thriller-horror-scroll")
        if "fantasy" in combined or axes["historical_world"] >= 4:
            return pick("romance-fantasy", "romance-polished")
        if "horror" in combined or "thriller" in combined:
            return pick("thriller-horror-scroll", "urban-drama")
        if "campus" in combined or "office" in combined:
            return pick("campus-office-drama", "urban-drama")
        if axes["warmth"] >= 4 and axes["plot"] <= 3:
            return pick("slice-of-life-soft-color", "romance-polished")
        return pick("urban-drama", "romance-polished")

    if style_id == "manhua":
        if axes["action"] >= 4 and ("china" in combined or "chinese" in combined or axes["historical_world"] >= 4):
            return pick("wuxia-action", "xianxia-fantasy")
        if "fantasy" in combined:
            return pick("xianxia-fantasy", "wuxia-action")
        if axes["historical_world"] >= 5:
            return pick("historical-elegant", "lianhuanhua-retro")
        if "memoir" in combined or "retro" in combined:
            return pick("lianhuanhua-retro", "ink-accented")
        if axes["abstract_ideas"] >= 4 or "society" in combined:
            return pick("social-realism", "modern-urban")
        return pick("modern-urban", "ink-accented")

    if style_id == "franco-belgian-bd":
        if axes["humor"] >= 4:
            return pick("marcinelle-comic-dynamic", "big-nose-humor")
        if "retro" in combined or "technology" in combined:
            return pick("atom-style-retro-modern", "brussels-clear-line")
        if axes["historical_world"] >= 4 and axes["action"] >= 3:
            return pick("realistic-adventure", "semi-realistic-travel")
        if "travel" in combined:
            return pick("semi-realistic-travel", "watercolor-album")
        if axes["warmth"] >= 4:
            return pick("watercolor-album", "brussels-clear-line")
        return pick("brussels-clear-line", "realistic-adventure")

    if style_id == "editorial":
        if "politic" in combined or "policy" in combined or "election" in combined:
            return pick("political-satire", "symbolic-minimal")
        if axes["text_density"] >= 4 and axes["abstract_ideas"] >= 4:
            return pick("symbolic-minimal", "infographic-explainer", "literary-graphic-essay")
        if axes["humor"] >= 4:
            return pick("dry-gag", "surreal-metaphor")
        if "literary" in combined or "memoir" in combined:
            return pick("literary-graphic-essay", "conceptual-texture")
        if axes["abstract_ideas"] >= 4:
            return pick("surreal-metaphor", "conceptual-texture")
        return pick("symbolic-minimal", "dry-gag")

    if style_id == "comic-strip":
        if axes["plot"] >= 4:
            return pick("continuity-story", "sunday-color")
        if axes["humor"] >= 4:
            return pick("gag-a-day", "single-panel-gag")
        if axes["warmth"] >= 4:
            return pick("warm-color-slice-of-life", "sunday-color")
        if "satire" in combined or "politic" in combined:
            return pick("satirical-strip", "gag-a-day")
        return pick("daily-bw", "gag-a-day")

    if style_id == "doodle":
        if axes["text_density"] >= 4 or axes["abstract_ideas"] >= 4:
            return pick("sketchnote-visual-notes", "annotated-knowledge", "whiteboard-explainer")
        if "diary" in combined or "memoir" in combined:
            return pick("diary-comic", "notebook-warm")
        if "business" in combined or "method" in combined:
            return pick("whiteboard-explainer", "annotated-knowledge")
        if axes["warmth"] >= 4:
            return pick("notebook-warm", "marker-color")
        return pick("notebook-warm", "zine-diy")

    if style_id == "retro-halftone":
        if "noir" in combined or "crime" in combined:
            return pick("noir-pulp-cover", "retro-romance-horror")
        if "war" in combined or "propaganda" in combined:
            return pick("war-propaganda-print", "american-golden-pulp")
        if axes["action"] >= 4:
            return pick("american-golden-pulp", "retro-romance-horror")
        if axes["abstract_ideas"] >= 4:
            return pick("benday-pop-print", "pop-poster")
        return pick("benday-pop-print", "cmyk-misregister")

    if style_id == "ink-sketch":
        if "noir" in combined or axes["emotion"] >= 4:
            return pick("crosshatch-noir", "literary-pen")
        if "portrait" in combined or "biography" in combined:
            return pick("fine-line-portrait", "literary-pen")
        if "travel" in combined:
            return pick("travel-journal", "ink-wash-muted")
        if "fable" in combined or "history" in combined:
            return pick("woodcut-expression", "literary-pen")
        if axes["warmth"] >= 4:
            return pick("ink-wash-muted", "literary-pen")
        return pick("literary-pen", "crosshatch-noir")

    return ordered[0]


def _brief_text(brief: ArtBrief | dict[str, object], key: str) -> str:
    if isinstance(brief, ArtBrief):
        return str(getattr(brief, key, "")).lower()
    return str(brief.get(key, "")).lower()


def _brief_combined(brief: ArtBrief | dict[str, object]) -> str:
    return " ".join(
        _brief_text(brief, key)
        for key in ("book_type", "time_period", "geography", "target_platform", "audience")
    )


def _brief_axes(brief: ArtBrief | dict[str, object]) -> dict[str, float]:
    if isinstance(brief, ArtBrief):
        raw = {
            "emotion": brief.emotional_intensity,
            "plot": brief.narrative_density,
            "abstract_ideas": brief.abstractness,
            "humor": brief.humor,
            "mobile": 5 if brief.target_platform in {"mobile", "card", "webtoon", "xhs"} else 3,
            "historical_world": max(brief.world_complexity, 4 if brief.time_period not in {"modern", "contemporary"} else 1),
            "text_density": brief.text_density,
            "premium_editorial": 5 if brief.book_type in {"philosophy", "literary", "social-science", "business"} else 3,
            "action": brief.action_intensity,
            "warmth": 4 if "general" in brief.audience or "大众" in brief.audience else 3,
        }
    else:
        raw = {key: brief.get(key, 3) for key in ("emotion", "plot", "abstract_ideas", "humor", "mobile", "historical_world", "text_density", "premium_editorial", "action", "warmth")}
    return {key: _clamp_score(value) for key, value in raw.items()}


def _hard_rule_style(axes: dict[str, float], brief: ArtBrief | dict[str, object]) -> str | None:
    combined = _brief_combined(brief)
    if axes["abstract_ideas"] >= 4 and axes["text_density"] >= 4 and axes["action"] <= 2:
        return "editorial"
    if (
        ("wuxia" in combined or "jianghu" in combined or "martial" in combined or "china" in combined)
        and axes["historical_world"] >= 4
        and axes["action"] >= 4
    ):
        return "manhua"
    if ("xianxia" in combined or "cultivation" in combined) and axes["historical_world"] >= 4:
        return "manhua"
    if axes["mobile"] >= 5 and axes["plot"] >= 4:
        return "webtoon-manhwa"
    if axes["historical_world"] >= 5 and axes["abstract_ideas"] >= 4:
        return "franco-belgian-bd"
    if axes["action"] >= 4 and axes["emotion"] >= 4:
        return "manga"
    if axes["humor"] >= 5 and axes["plot"] <= 3:
        return "comic-strip"
    return None


def _clamp_score(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 3.0
    return max(0.0, min(5.0, number))


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
