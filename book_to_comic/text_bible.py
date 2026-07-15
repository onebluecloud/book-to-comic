from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any

from .models import Panel


LONG_FORM_KEYS = ("dialogue", "scene_setting", "interior_monologue", "connective_prose", "narration", "reality_mapping", "comment_hook")
CARD_FORM_KEYS = ("dialogue", "card_copy", "narration", "reality_mapping", "comment_hook")


def normalize_story_panel_for_package(panel: Mapping[str, Any]) -> dict[str, Any]:
    dialogue = _string_list(panel.get("dialogue")) or _layer_lines(panel, "dialogue")
    long_lines = panel_long_form_lines(panel)
    card_lines = panel_card_form_lines(panel)
    result = {
        "index": int(panel.get("index") or 0),
        "beat": _text(panel.get("beat")),
        "visual": _text(panel.get("visual") or panel.get("action")),
        "dialogue": dialogue,
        "narration": _text(panel.get("narration")),
        "comment_hook": _text(panel.get("comment_hook")),
        "scene_setting": _text(panel.get("scene_setting")) or _layer_text(panel, "scene_setting"),
        "interior_monologue": _text(panel.get("interior_monologue")) or _layer_text(panel, "interior_monologue"),
        "connective_prose": _text(panel.get("connective_prose")) or _layer_text(panel, "connective_prose"),
        "reality_mapping": _text(panel.get("reality_mapping")) or _layer_text(panel, "reality_mapping"),
        "card_copy": card_lines,
        "long_copy": long_lines,
        "invented_dialogue": _string_list(panel.get("invented_dialogue")),
    }
    if not result["narration"] and long_lines:
        excluded = set(dialogue + [result["comment_hook"]])
        result["narration"] = "\n".join(line for line in long_lines if line not in excluded)
    return result


def panel_long_form_lines(panel: Panel | Mapping[str, Any]) -> list[str]:
    variant = _variant_lines(panel, "long_form")
    if variant:
        return variant
    # Panel dataclasses carry the long_form snapshot in long_copy (mirror of
    # card_copy). Without this step every dataclass render skipped text_variants
    # and dumped the internal LONG_FORM_KEYS concat into reader captions.
    long_copy = _field_lines(panel, "long_copy")
    if long_copy:
        return _dedupe(long_copy)
    lines = _lines_by_keys(panel, LONG_FORM_KEYS)
    return _dedupe(lines)


def panel_card_form_lines(panel: Panel | Mapping[str, Any]) -> list[str]:
    variant = _variant_lines(panel, "card_form")
    if variant:
        return _dedupe(variant)
    card_copy = _field_lines(panel, "card_copy")
    if card_copy:
        return _dedupe(card_copy)
    lines = _lines_by_keys(panel, CARD_FORM_KEYS)
    return _dedupe(lines)


def panel_text_metrics(panel: Panel | Mapping[str, Any]) -> dict[str, int]:
    long_lines = panel_long_form_lines(panel)
    card_lines = panel_card_form_lines(panel)
    return {
        "long_form_chars": _char_count(long_lines),
        "card_form_chars": _char_count(card_lines),
        "long_form_paragraphs": len(long_lines),
        "card_form_paragraphs": len(card_lines),
    }


def _variant_lines(panel: Panel | Mapping[str, Any], name: str) -> list[str]:
    if not isinstance(panel, Mapping):
        return []
    variants = panel.get("text_variants")
    if not isinstance(variants, Mapping):
        return []
    return _string_list(variants.get(name))


def _lines_by_keys(panel: Panel | Mapping[str, Any], keys: tuple[str, ...]) -> list[str]:
    lines: list[str] = []
    for key in keys:
        lines.extend(_field_lines(panel, key))
        if isinstance(panel, Mapping):
            lines.extend(_layer_lines(panel, key))
    return lines


def _field_lines(panel: Panel | Mapping[str, Any], key: str) -> list[str]:
    value: object
    if isinstance(panel, Mapping):
        value = panel.get(key)
    else:
        value = getattr(panel, key, "")
    return _string_list(value)


def _layer_lines(panel: Mapping[str, Any], key: str) -> list[str]:
    layers = panel.get("text_layers")
    if not isinstance(layers, Mapping):
        return []
    return _string_list(layers.get(key))


def _layer_text(panel: Mapping[str, Any], key: str) -> str:
    return "\n".join(_layer_lines(panel, key))


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [line.strip() for line in value.splitlines() if line.strip()]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _dedupe(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for line in lines:
        cleaned = _text(line)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def _char_count(lines: list[str]) -> int:
    return len(re.sub(r"\s+", "", "".join(lines)))


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()
