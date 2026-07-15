import json
from pathlib import Path
from typing import Any

from .models import AdaptationPackage, Character, CoreIdea, Panel, Suitability
from .styles import get_style
from .text_bible import normalize_story_panel_for_package


def package_from_json(path: str | Path) -> AdaptationPackage:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return package_from_dict(data)


def package_from_dict(data: dict[str, Any]) -> AdaptationPackage:
    _assert_known_keys(
        data,
        {
            "book_title",
            "author",
            "episode_title",
            "suitability",
            "covered_points",
            "core_ideas",
            "methods",
            "light_shell",
            "hard_core",
            "characters",
            "character_relationship",
            "storyboard",
            "title_candidates",
            "style_id",
        },
        "$",
    )
    return AdaptationPackage(
        book_title=str(data["book_title"]),
        author=str(data.get("author", "")),
        episode_title=str(data["episode_title"]),
        suitability=_suitability_from_dict(data["suitability"]),
        covered_points=tuple(str(item) for item in data["covered_points"]),
        core_ideas=tuple(_core_idea_from_dict(item) for item in data["core_ideas"]),
        methods=tuple(str(item) for item in data["methods"]),
        light_shell=str(data["light_shell"]),
        hard_core=str(data["hard_core"]),
        characters=tuple(_character_from_dict(item) for item in data["characters"]),
        character_relationship=str(data["character_relationship"]),
        storyboard=tuple(_panel_from_dict(item) for item in data["storyboard"]),
        title_candidates=tuple(str(item) for item in data["title_candidates"]),
        style_id=str(data.get("style_id", "editorial")),
    )


def validate_package(package: AdaptationPackage) -> list[str]:
    errors: list[str] = []
    if not package.suitability.is_applicable:
        errors.append("suitability.is_applicable must be true for a comic package")
    if not 4 <= len(package.storyboard) <= 16:
        errors.append("storyboard must contain 4-16 panels")

    expected_indexes = list(range(1, len(package.storyboard) + 1))
    actual_indexes = [panel.index for panel in package.storyboard]
    if actual_indexes != expected_indexes:
        errors.append(f"storyboard panel indexes must be 1..N, got {actual_indexes}")

    if not package.core_ideas:
        errors.append("core_ideas must contain at least one idea")
    if not package.characters:
        errors.append("characters must contain at least one character")
    for character in package.characters:
        if not character.prompt_fragment.strip():
            errors.append(f"character '{character.name}' must include prompt_fragment")
    if not package.title_candidates:
        errors.append("title_candidates must contain at least one title")

    try:
        get_style(package.style_id)
    except ValueError as exc:
        errors.append(str(exc))

    return errors


def _suitability_from_dict(data: dict[str, Any]) -> Suitability:
    _assert_known_keys(data, {"is_applicable", "category", "reason"}, "$.suitability")
    if not isinstance(data["is_applicable"], bool):
        raise TypeError("$.suitability.is_applicable must be a boolean")
    return Suitability(
        is_applicable=data["is_applicable"],
        category=str(data["category"]),
        reason=str(data["reason"]),
    )


def _core_idea_from_dict(data: dict[str, Any]) -> CoreIdea:
    _assert_known_keys(data, {"title", "kernel", "dramatization"}, "$.core_ideas[]")
    return CoreIdea(
        title=str(data["title"]),
        kernel=str(data["kernel"]),
        dramatization=str(data["dramatization"]),
    )


def _character_from_dict(data: dict[str, Any]) -> Character:
    _assert_known_keys(data, {"name", "concept", "visual", "personality", "prompt_fragment"}, "$.characters[]")
    return Character(
        name=str(data["name"]),
        concept=str(data["concept"]),
        visual=str(data["visual"]),
        personality=str(data["personality"]),
        prompt_fragment=str(data["prompt_fragment"]),
    )


def _panel_from_dict(data: dict[str, Any]) -> Panel:
    _assert_known_keys(
        data,
        {
            "index",
            "beat",
            "visual",
            "dialogue",
            "narration",
            "comment_hook",
            "scene_setting",
            "interior_monologue",
            "connective_prose",
            "reality_mapping",
            "card_copy",
            "invented_dialogue",
            "text_layers",
            "text_variants",
            "text_budgets",
            "text_metrics",
            "text_requirements",
            "copy_jobs",
        },
        "$.storyboard[]",
    )
    normalized = normalize_story_panel_for_package(data)
    return Panel(
        index=normalized["index"],
        beat=str(normalized["beat"]),
        visual=str(normalized["visual"]),
        dialogue=tuple(str(item) for item in normalized.get("dialogue", ())),
        narration=str(normalized.get("narration", "")),
        comment_hook=str(normalized.get("comment_hook", "")),
        scene_setting=str(normalized.get("scene_setting", "")),
        interior_monologue=str(normalized.get("interior_monologue", "")),
        connective_prose=str(normalized.get("connective_prose", "")),
        reality_mapping=str(normalized.get("reality_mapping", "")),
        card_copy=tuple(str(item) for item in normalized.get("card_copy", ())),
        long_copy=tuple(str(item) for item in normalized.get("long_copy", ())),
        invented_dialogue=tuple(str(item) for item in normalized.get("invented_dialogue", ())),
    )


def _assert_known_keys(data: dict[str, Any], allowed: set[str], path: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        joined = ", ".join(unknown)
        raise KeyError(f"{path} contains unknown field(s): {joined}")
