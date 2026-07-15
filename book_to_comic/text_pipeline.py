from __future__ import annotations

from collections.abc import Mapping
from typing import Any


SCHEMA_VERSION = "3.0"


def build_text_layers(panel: Mapping[str, Any]) -> dict[str, Any]:
    layers = panel.get("text_layers")
    result: dict[str, Any] = dict(layers) if isinstance(layers, Mapping) else {}
    result.setdefault("scene_setting", _text(panel.get("scene_setting")))
    result.setdefault("narration", _text(panel.get("narration")))
    result.setdefault("interior_monologue", _text(panel.get("interior_monologue")))
    result.setdefault("connective_prose", _text(panel.get("connective_prose")))
    result.setdefault("dialogue", _string_list(panel.get("dialogue")))
    result.setdefault("caption", _text(panel.get("comment_hook")))
    result.setdefault("card_copy", _string_list(panel.get("card_copy")))
    return {key: value for key, value in result.items() if _has_content(value)}


def build_text_variants(panel: Mapping[str, Any]) -> list[dict[str, Any]]:
    variants = panel.get("text_variants")
    if isinstance(variants, list) and variants:
        return [dict(item) for item in variants if isinstance(item, Mapping)]
    layers = build_text_layers(panel)
    result: list[dict[str, Any]] = []
    long_form = [
        layers.get("scene_setting"),
        layers.get("narration"),
        layers.get("interior_monologue"),
        layers.get("connective_prose"),
    ]
    card_form = [layers.get("caption"), *(_string_list(layers.get("card_copy")))]
    if any(_has_content(item) for item in long_form):
        result.append({"variant_id": "long_form", "purpose": "long-scroll", "blocks": [str(item) for item in long_form if _has_content(item)]})
    if any(_has_content(item) for item in card_form):
        result.append({"variant_id": "card_form", "purpose": "card", "blocks": [str(item) for item in card_form if _has_content(item)]})
    dialogue = _string_list(layers.get("dialogue"))
    if dialogue:
        result.append({"variant_id": "dialogue", "purpose": "lettering", "blocks": dialogue})
    return result


def normalize_panel_text(panel: dict[str, Any]) -> dict[str, Any]:
    updated = dict(panel)
    updated["text_layers"] = build_text_layers(panel)
    variants = build_text_variants(updated)
    if variants:
        updated["text_variants"] = variants
    return updated


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if str(value or "").strip():
        return [str(value).strip()]
    return []


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _has_content(value: object) -> bool:
    if isinstance(value, list):
        return any(_has_content(item) for item in value)
    if isinstance(value, Mapping):
        return any(_has_content(item) for item in value.values())
    return bool(str(value or "").strip())
