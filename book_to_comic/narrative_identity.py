from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from .caption_budget import (
    CARD_FORM_AVG_MIN,
    CARD_FORM_TARGET_MAX,
    LONG_FORM_TARGET_MAX,
    LONG_FORM_TARGET_MIN,
)


SCHEMA_VERSION = "2.0"
PENDING_STATUS = "needs_host_planning"
READY_STATUS = "ready"
NARRATIVE_IDENTITY_RELATIVE_PATH = Path("planning") / "narrative_identity.json"

# Languages the pipeline knows how to prompt, QA, and package end-to-end
# (caption prompts, text budgets, output filenames, EPUB metadata). zh-CN is
# the original/default target; "en" was added so the project is usable for
# English-language comics without forking the language out by hand.
# Contributing a new language means wiring it through text_prompt_compiler.py,
# project_prompts.py, and delivery.py, then adding its code here.
DEFAULT_LANGUAGE = "zh-CN"
SUPPORTED_LANGUAGES = ("zh-CN", "en")

# Voice profile picks the caption REGISTER by book type. There is no single
# right register: the storyteller opening that carries 卖炭翁 sounds absurd on
# 《被讨厌的勇气》, whose best captions open on a pain-point line of dialogue.
# Left unset, the host falls back to the generic guidance in SKILL.md.
VOICE_PROFILES = ("narrative", "conceptual", "literary", "juvenile")


class NarrativeIdentityError(ValueError):
    """Raised when a project narrative identity is missing or not production-ready."""


def empty_narrative_identity(book_title: str = "", language: str = DEFAULT_LANGUAGE) -> dict[str, Any]:
    if language not in SUPPORTED_LANGUAGES:
        raise NarrativeIdentityError(
            f"language must be one of {', '.join(SUPPORTED_LANGUAGES)}, got {language!r}"
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "planning_status": PENDING_STATUS,
        "book_title": book_title,
        "language": language,
        "voice_core": {
            "narrative_voice": "",
            "why_specific_to_this_book": "",
            "reader_bridge_policy": "",
            "voice_profile": "",
            "tone_matrix": [],
        },
        "speaker_registers": [],
        "forbidden_generic_phrases": [],
        "forbidden_cross_book_phrases": [],
        # Calibrated against 85 panels of hand-reviewed scripts (caption_budget.py).
        # The old 90-160 default covered 1% of those captions and taught every new
        # project to water-fill and editorialize.
        "panel_text_policy": {
            "long_form_min_chars": LONG_FORM_TARGET_MIN,
            "long_form_max_chars": LONG_FORM_TARGET_MAX,
            "card_form_min_chars": CARD_FORM_AVG_MIN,
            "card_form_max_chars": CARD_FORM_TARGET_MAX,
            "max_card_paragraphs": 3,
        },
        "host_planning_required": [
            "book-specific voice and register",
            "forbidden reusable copy",
            "long_form/card_form text budgets",
        ],
    }


def load_narrative_identity(project: str | Path) -> dict[str, Any]:
    path = Path(project) / NARRATIVE_IDENTITY_RELATIVE_PATH
    if not path.exists():
        raise FileNotFoundError(f"Required narrative identity is missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise NarrativeIdentityError(f"Narrative identity must be a JSON object: {path}")
    return data


def validate_narrative_identity(
    project: str | Path,
    *,
    raise_on_fail: bool = True,
    write_report: bool = True,
) -> dict[str, Any]:
    root = Path(project)
    errors: list[str] = []
    warnings: list[str] = []
    identity: dict[str, Any] = {}
    identity_hash = ""

    try:
        identity = load_narrative_identity(root)
        identity_hash = narrative_identity_sha256(identity)
    except (FileNotFoundError, OSError, json.JSONDecodeError, NarrativeIdentityError) as exc:
        errors.append(str(exc))

    if identity:
        status = str(identity.get("planning_status", "")).strip()
        if status == PENDING_STATUS:
            errors.append("narrative_identity.planning_status is needs_host_planning")
        elif status != READY_STATUS:
            errors.append("narrative_identity.planning_status must be ready")

        if str(identity.get("language", "")).strip() not in SUPPORTED_LANGUAGES:
            errors.append(f"narrative_identity.language must be one of {', '.join(SUPPORTED_LANGUAGES)}")

        voice_core = identity.get("voice_core")
        if not isinstance(voice_core, Mapping) or not voice_core:
            errors.append("voice_core must be a non-empty object")
            voice_core = {}
        why = str(voice_core.get("why_specific_to_this_book") or "").strip()
        if len(why) < 30:
            errors.append("voice_core.why_specific_to_this_book is too generic or too short")

        profile = str(voice_core.get("voice_profile") or "").strip()
        if profile and profile not in VOICE_PROFILES:
            errors.append(f"voice_core.voice_profile must be one of {', '.join(VOICE_PROFILES)}")
        elif not profile:
            warnings.append(
                "voice_core.voice_profile is unset; pick one of "
                f"{', '.join(VOICE_PROFILES)} so the caption register matches the book type"
            )

        if not _string_list(identity.get("forbidden_generic_phrases")):
            errors.append("forbidden_generic_phrases must contain at least one item")
        if not _string_list(identity.get("forbidden_cross_book_phrases")):
            errors.append("forbidden_cross_book_phrases must contain at least one item")
        if not _speaker_registers(identity.get("speaker_registers")):
            errors.append("speaker_registers must contain at least one register")

        policy = identity.get("panel_text_policy")
        if not isinstance(policy, Mapping):
            errors.append("panel_text_policy must be a non-empty object")
            policy = {}
        if int(policy.get("max_card_paragraphs", 0) or 0) != 3:
            errors.append("panel_text_policy.max_card_paragraphs must be 3")
        for low_key, high_key in (
            ("card_form_min_chars", "card_form_max_chars"),
            ("long_form_min_chars", "long_form_max_chars"),
        ):
            low = _positive_int(policy.get(low_key))
            high = _positive_int(policy.get(high_key))
            if not low or not high or low >= high:
                errors.append(f"panel_text_policy {low_key}/{high_key} must be positive and ordered")
        card_max = _positive_int(policy.get("card_form_max_chars"))
        long_max = _positive_int(policy.get("long_form_max_chars"))
        if card_max and long_max and long_max <= card_max:
            warnings.append("long_form_max_chars should be larger than card_form_max_chars")

    passed = not errors
    report = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": _now(),
        "passed": passed,
        "status": "passed" if passed else "failed",
        "narrative_identity_sha256": identity_hash,
        "summary": narrative_identity_summary(identity) if identity else {},
        "errors": errors,
        "warnings": warnings,
    }
    if write_report:
        _write_json(root / "qa" / "narrative-identity-report.json", report)
    if raise_on_fail and not passed:
        raise NarrativeIdentityError("; ".join(errors) or "Narrative identity validation failed.")
    return report


def narrative_identity_sha256(project_or_identity: str | Path | Mapping[str, Any]) -> str:
    if isinstance(project_or_identity, Mapping):
        identity = dict(project_or_identity)
    else:
        identity = load_narrative_identity(project_or_identity)
    encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def narrative_identity_summary(identity: Mapping[str, Any]) -> dict[str, str]:
    voice_core = identity.get("voice_core", {})
    policy = identity.get("panel_text_policy", {})
    return {
        "book_title": str(identity.get("book_title") or "").strip(),
        "language": str(identity.get("language") or "").strip(),
        "narrative_voice": _join(voice_core.get("narrative_voice") if isinstance(voice_core, Mapping) else ""),
        "voice_profile": _join(voice_core.get("voice_profile") if isinstance(voice_core, Mapping) else ""),
        "why_specific_to_this_book": _join(voice_core.get("why_specific_to_this_book") if isinstance(voice_core, Mapping) else ""),
        "reader_bridge_policy": _join(voice_core.get("reader_bridge_policy") if isinstance(voice_core, Mapping) else ""),
        "tone_matrix": _join(voice_core.get("tone_matrix") if isinstance(voice_core, Mapping) else ""),
        "speaker_registers": _join(identity.get("speaker_registers")),
        "forbidden_generic_phrases": _join(identity.get("forbidden_generic_phrases")),
        "forbidden_cross_book_phrases": _join(identity.get("forbidden_cross_book_phrases")),
        "panel_text_policy": _join(policy),
    }


def _speaker_registers(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray, str)):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping) and any(str(v).strip() for v in item.values())]


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _positive_int(value: object) -> int:
    return value if isinstance(value, int) and value > 0 else 0


def _join(value: object) -> str:
    if isinstance(value, Mapping):
        parts = []
        for key in sorted(value):
            text = _join(value[key])
            if text:
                parts.append(f"{key}: {text}")
        return "; ".join(parts)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "").strip()


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
