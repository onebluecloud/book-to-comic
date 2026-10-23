from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from typing import Any

from .caption_budget import LONG_FORM_TARGET_MAX, LONG_FORM_TARGET_MIN
from .narrative_identity import DEFAULT_LANGUAGE
from .prompt_compiler import narrative_identity_lock_lines
from .text_qa import DEFAULT_CARD_MAX_CHARS, DEFAULT_LONG_MAX_CHARS, DEFAULT_THRESHOLDS, PER_PANEL_MIN_CHARS


def _prompt_language(narrative_identity: Mapping[str, Any] | None) -> str:
    if not isinstance(narrative_identity, Mapping):
        return DEFAULT_LANGUAGE
    language = str(narrative_identity.get("language") or "").strip()
    return language or DEFAULT_LANGUAGE


def _panel_text_task_lines(panel_id: str, language: str) -> list[str]:
    if language == "en":
        return [
            f"Task: write English post-production lettering for comic panel {panel_id}.",
            "Language: en.",
        ]
    return [
        f"Task: write Chinese post-production lettering for comic panel {panel_id}.",
        "Language: zh-CN.",
    ]


def _panel_text_budget_lines(language: str) -> list[str]:
    if language == "en":
        return [
            (
                f"- long_form: target {LONG_FORM_TARGET_MIN}-{LONG_FORM_TARGET_MAX} characters per panel, "
                "written like a storyteller addressing listeners, not expository prose or an essay's "
                f"conclusion; hard floor {PER_PANEL_MIN_CHARS} per panel, hard ceiling {DEFAULT_LONG_MAX_CHARS}, "
                f"episode average must not fall below {DEFAULT_THRESHOLDS['avg_long_min_chars']}; "
                "used for long image/review/production narrative."
            ),
            f"- card_form: mobile card copy; max 3 paragraphs; per-panel ceiling {DEFAULT_CARD_MAX_CHARS} characters; short character dialogue / plain-language explanation / real-life mapping.",
            "- Do not repeat the same phrase across panels; the second layer must add new information; avoid translation-ese; keep poetic original lines verbatim instead of breaking them into a list.",
            "- **The punchline must be felt**: give imagery, physical sensation, or a concrete consequence "
            "(e.g. \"ten fingers, stained black for good\" / \"a fixed persona like armor\"), not a floating "
            "conceptual claim. Every panel's copy must touch a real person, action, or prop that actually "
            "exists in this panel's artwork.",
        ]
    return [
        (
            f"- long_form: 目标每格 {LONG_FORM_TARGET_MIN}-{LONG_FORM_TARGET_MAX} 个中文字符，"
            f"像说书人讲给听众，不是说明文，也不是论文结论；单格硬下限 {PER_PANEL_MIN_CHARS}、"
            f"硬上限 {DEFAULT_LONG_MAX_CHARS}，整集平均不得低于 {DEFAULT_THRESHOLDS['avg_long_min_chars']}；"
            "used for long image/review/production narrative."
        ),
        f"- card_form: mobile card copy; max 3 paragraphs; 单格上限 {DEFAULT_CARD_MAX_CHARS} 字; short角色台词 / 大白话解释 / 现实映射.",
        "- 禁止跨格复读同一短语；第二层必须给新信息；不写翻译腔；诗意原句保留原文不要拆成清单.",
        "- **点睛句必须可感**：给意象、身体感或具体后果（「十根手指，黑得再也洗不回来」「固定人设像盔甲」），"
        "不要给悬空的概念论断（「寻找便开始替代最初的惊异」）。每格文案必须至少碰到本格画面里真实存在的人、动作或道具。",
    ]


def compile_panel_text_prompt(
    panel: Mapping[str, Any],
    *,
    narrative_identity: Mapping[str, Any] | None = None,
    episode: Mapping[str, Any] | None = None,
    scene: Mapping[str, Any] | None = None,
    previous_panel: Mapping[str, Any] | None = None,
    next_panel: Mapping[str, Any] | None = None,
) -> str:
    panel_id = str(panel.get("panel_id") or f"P{int(panel.get('index') or 0):02d}")
    language = _prompt_language(narrative_identity)
    lines = [
        *_panel_text_task_lines(panel_id, language),
        *narrative_identity_lock_lines(narrative_identity),
        "Write text for two separate outputs:",
        # Budget comes from caption_budget.py (calibrated on 85 hand-reviewed
        # panels). The prompt and the QA gate must never disagree again.
        *_panel_text_budget_lines(language),
        "Do not reuse generic cross-book phrases. Do not cheapen classics with clickbait, shock copy, or chicken-soup slogans.",
        "Use concrete scene, psychology, cause-effect bridge, plain-language translation, and a defensible reader-life bridge.",
        "Source refs:",
        json.dumps(_string_list(panel.get("source_refs")), ensure_ascii=False),
        "Text budget:",
        json.dumps(_text_budget(panel, narrative_identity), ensure_ascii=False, indent=2),
        "Forbidden phrases:",
        json.dumps(_forbidden_phrases(narrative_identity), ensure_ascii=False, indent=2),
        "Semantic anchors:",
        json.dumps(panel.get("semantic_anchors", []), ensure_ascii=False, indent=2),
        "Previous panel context:",
        json.dumps(_compact_panel(previous_panel), ensure_ascii=False, indent=2),
        "Next panel context:",
        json.dumps(_compact_panel(next_panel), ensure_ascii=False, indent=2),
        "Return strict JSON only with this shape:",
        _json_schema_example(),
        "Episode context:",
        json.dumps(_compact_episode(episode), ensure_ascii=False, indent=2),
        "Scene context:",
        json.dumps(_compact_scene(scene), ensure_ascii=False, indent=2),
        "Panel source:",
        json.dumps(dict(panel), ensure_ascii=False, indent=2),
    ]
    return "\n".join(line for line in lines if line).strip() + "\n"


def compile_scene_text_prompt(
    scene: Mapping[str, Any],
    *,
    narrative_identity: Mapping[str, Any] | None = None,
    episode: Mapping[str, Any] | None = None,
) -> str:
    language = _prompt_language(narrative_identity)
    lines = [
        f"Task: run a scene-level {language} text pass for comic scene {scene.get('scene_id', '')}.",
        *narrative_identity_lock_lines(narrative_identity),
        "For each panel, produce text_layers and text_variants. Keep card_form <= 3 paragraphs; let long_form carry richer context.",
        "Check scene continuity: every panel should connect to previous action, not read like isolated article cards.",
        "Return strict JSON only: {\"scene_id\":\"...\",\"panels\":[{\"panel_id\":\"...\",\"text_layers\":{},\"text_variants\":{},\"text_notes\":[]}]}",
        "Episode context:",
        json.dumps(_compact_episode(episode), ensure_ascii=False, indent=2),
        "Scene source:",
        json.dumps(dict(scene), ensure_ascii=False, indent=2),
    ]
    return "\n".join(line for line in lines if line).strip() + "\n"


def _json_schema_example() -> str:
    return json.dumps(
        {
            "panel_id": "P01",
            "text_layers": {
                "dialogue": [],
                "scene_setting": "",
                "interior_monologue": "",
                "connective_prose": "",
                "narration": "",
                "reality_mapping": "",
                "comment_hook": "",
            },
            "text_variants": {
                "long_form": [],
                "card_form": [],
            },
            "invented_dialogue": [],
            "text_notes": [],
        },
        ensure_ascii=False,
        indent=2,
    )


def _compact_episode(episode: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(episode, Mapping):
        return {}
    keys = ("book_title", "episode_title", "primary_thesis", "adaptation_strategy", "narrative_spine")
    return {key: episode.get(key) for key in keys if key in episode}


def _compact_scene(scene: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(scene, Mapping):
        return {}
    keys = ("scene_id", "location", "event", "concept_carried", "escalation_role", "callback_to_spine_event")
    return {key: scene.get(key) for key in keys if key in scene}


def _compact_panel(panel: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(panel, Mapping):
        return {}
    keys = ("panel_id", "beat", "panel_role", "action", "emotion", "source_refs", "semantic_anchors")
    return {key: panel.get(key) for key in keys if key in panel}


def _text_budget(panel: Mapping[str, Any], narrative_identity: Mapping[str, Any] | None) -> dict[str, Any]:
    policy = narrative_identity.get("panel_text_policy", {}) if isinstance(narrative_identity, Mapping) else {}
    budget = panel.get("text_budgets")
    return {
        "policy": policy if isinstance(policy, Mapping) else {},
        "panel_text_budgets": budget if isinstance(budget, Mapping) else {},
        "balloon_budget": panel.get("balloon_budget") if isinstance(panel.get("balloon_budget"), Mapping) else {},
        "max_card_paragraphs": (policy.get("max_card_paragraphs") if isinstance(policy, Mapping) else 3) or 3,
    }


def _forbidden_phrases(narrative_identity: Mapping[str, Any] | None) -> dict[str, list[str]]:
    if not isinstance(narrative_identity, Mapping):
        return {"generic": [], "cross_book": []}
    return {
        "generic": _string_list(narrative_identity.get("forbidden_generic_phrases")),
        "cross_book": _string_list(narrative_identity.get("forbidden_cross_book_phrases")),
    }


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []
