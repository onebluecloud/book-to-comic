from __future__ import annotations

from .styles import get_style


COMMON_QA_RUBRIC = (
    "style_signature",
    "character_identity",
    "anatomy_and_hands",
    "environment_continuity",
    "prop_accuracy",
    "composition_readability",
    "shot_variety",
    "text_contamination",
    "lettering_safe_zone",
    "final_finish",
)


def style_specific_qa_rules(style_id: str) -> dict[str, tuple[str, ...]]:
    style = get_style(style_id)
    return {
        "rubric": COMMON_QA_RUBRIC,
        "signature": tuple(style.qa.get("signature", ())),
        "hard_fail": tuple(style.qa.get("hard_fail", ())),
    }


def prompt_text_failures(style_id: str, prompt: str) -> tuple[str, ...]:
    text = prompt.lower()
    failures: list[str] = []
    if "readable text" not in text or "pseudo-text" not in text:
        failures.append("missing text-contamination guard")
    if style_id == "doodle" and "stick figures" not in text:
        failures.append("doodle missing stick-figure guard")
    if style_id == "retro-halftone" and "halftone" not in text:
        failures.append("retro-halftone missing print-system guard")
    if style_id == "franco-belgian-bd" and "round-headed" not in text and "round heads" in text:
        failures.append("bd still suggests generic round heads")
    return tuple(failures)
