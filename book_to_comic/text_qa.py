from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
import re
from pathlib import Path
from typing import Any

from .caption_budget import (
    CARD_FORM_AVG_MIN,
    CARD_FORM_HARD_MIN,
    CARD_FORM_TARGET_MAX,
    LONG_FORM_AVG_MIN,
    LONG_FORM_HARD_MAX,
    LONG_FORM_HARD_MIN,
    clamp_card_max,
    clamp_long_max,
)
from .narrative_identity import load_narrative_identity
from .project_layout import load_episode
from .story_gate import flatten_episode_panels
from .text_bible import (
    normalize_story_panel_for_package,
    panel_card_form_lines,
    panel_long_form_lines,
    panel_text_metrics,
)


# Camera/staging vocabulary that belongs in image prompts, never in reader-facing
# captions. Matched at line start only ("画面：…"), so prose that merely mentions
# 画面/镜头 mid-sentence is not flagged. Root cause: hosts copying a storyboard's
# 【画面】 column straight into text_variants (the 卖炭翁 incident, 2026-07-08).
_STAGE_DIRECTION_PREFIXES = (
    "画面", "镜头", "构图", "景深", "运镜", "分镜",
    "大远景", "远景", "全景", "中景", "中近景", "近景", "特写",
    "俯拍", "仰拍", "侧拍", "过肩", "低角度", "高角度", "回忆格",
)
_STAGE_DIRECTION_RE = re.compile(
    "^(?:" + "|".join(_STAGE_DIRECTION_PREFIXES) + ")[：:]"
)


# Caption budget lives in caption_budget.py — calibrated against 85 panels of
# hand-reviewed scripts. Re-exported here so existing importers keep
# working; do not fork the numbers.
DEFAULT_THRESHOLDS = {
    "avg_long_min_chars": LONG_FORM_AVG_MIN,
    "avg_card_min_chars": CARD_FORM_AVG_MIN,
    "scene_setting_coverage": 0.6,
    "connective_coverage": 0.5,
    "emotional_coverage": 0.6,
    "inner_monologue_applicable_coverage": 1.0,
    "card_form_overflow_rate": 0.05,
}
DEFAULT_CARD_MAX_CHARS = CARD_FORM_TARGET_MAX
DEFAULT_LONG_MAX_CHARS = LONG_FORM_HARD_MAX
PER_PANEL_MIN_CHARS = LONG_FORM_HARD_MIN
PER_PANEL_CARD_MIN_CHARS = CARD_FORM_HARD_MIN

RULES_PATH = Path(__file__).resolve().parent / "presets" / "text_quality_rules.json"
REPEATED_TEMPLATE_PATTERNS = (
    re.compile(r"真正的.+不是.+而是"),
    re.compile(r"你以为.+其实"),
    re.compile(r"问题从来不是.+而是"),
    re.compile(r"^很多时候"),
)
NEGATION_TOKENS = ("不", "没", "无", "非", "勿", "别", "未")

# Concrete-anchor gate (2026-07-09). A caption that never touches ANY person,
# action or prop actually drawn in its own panel is a free-floating essay line.
# Deliberate scope: this only catches the extreme case (a panel whose entire
# long_form shares no concrete word with its own staging). It cannot judge
# taste — whether a payoff line lands as an IMAGE ("固定人设像盔甲") or as a bare
# CONCEPT ("寻找便开始替代最初的惊异"). Measured on two real books, a regex for
# 「不是X而是Y」 verdict phrasing fired on 50% of panels in a narrative book and
# 58% in a concept book, i.e. it would punish concept books hardest — so that
# regex is NOT a gate. Taste lives in SKILL.md's few-shot, not here.
# Fields that describe what the panel ACTUALLY draws. Schema-3 keeps the staging
# in `visual` (中文全景描述); props_and_states carries Chinese in its VALUES
# ("PROP-OAR": "横停在右侧船舷"). The trailing names are schema-2 equivalents.
#
# Deliberately EXCLUDED: cause / effect / anchor_note. Those are narration, and
# they carry abstract verbs — `effect` on 桃花源记 P01 reads "渔人停止划水，抬头
# 寻找花瓣来源", whose 「寻找」 collides with an essay caption "寻找便开始替代最初
# 的惊异" and hands the gate a false pass. Staging means things you can draw.
_ANCHOR_FIELDS = (
    "visual", "observable_change", "action_verb", "props_and_states",
    "focal_point", "foreground", "midground", "props",
)
# Function words: a bigram containing one of these is grammar, not a concrete noun.
_ANCHOR_STOP_CHARS = frozenset("的了在是和与就也都不一个这那有着被把从对上下中里之其所为以于而且但很再又已还没或")
_CJK_BLOCK_RE = re.compile(r"[一-鿿]{2,}")
NUMBER_PATTERN = re.compile(r"(?:\d+(?:\.\d+)?|[零一二三四五六七八九十百千万亿两]+)(?:个|页|年|章|节|次|%|％)?")


class LetteringFidelityError(ValueError):
    def __init__(self, message: str, report: dict[str, Any]):
        super().__init__(message)
        self.report = report


def validate_text_richness(
    project: str | Path,
    *,
    raise_on_fail: bool = True,
    write_report: bool = True,
) -> dict[str, Any]:
    root = Path(project)
    episode = _load_episode(root)
    panels = [panel for panel in flatten_episode_panels(episode) if isinstance(panel, dict)]
    identity = _load_identity_or_empty(root)
    rules = _load_rules()
    policy = identity.get("panel_text_policy", {}) if isinstance(identity, Mapping) else {}
    # A host policy may TIGHTEN the per-panel caps, never loosen them. Before
    # this clamp, a project declaring long_form_max_chars=160 simply switched the
    # over-length gate off — which is how 桃花源记 shipped 93-char essay captions.
    card_max_chars = clamp_card_max(policy.get("card_form_max_chars") if isinstance(policy, Mapping) else None)
    long_max_chars = clamp_long_max(policy.get("long_form_max_chars") if isinstance(policy, Mapping) else None)
    thresholds = dict(DEFAULT_THRESHOLDS)
    # A book may ask for a denser average than the default, but never past the
    # body target — 桃花源记 declared long_form_min_chars=90, which demanded an
    # average LONGER than the per-panel hard cap and forced essay captions.
    from .caption_budget import LONG_FORM_TARGET_MAX

    long_rules = rules.get("long_form", {}) if isinstance(rules.get("long_form"), Mapping) else {}
    for candidate in (
        long_rules.get("min_average_chars"),
        policy.get("long_form_min_chars") if isinstance(policy, Mapping) else None,
    ):
        if isinstance(candidate, int) and thresholds["avg_long_min_chars"] < candidate <= LONG_FORM_TARGET_MAX:
            thresholds["avg_long_min_chars"] = candidate
    forbidden_phrases = _string_list(rules.get("forbidden_generic_phrases"))
    forbidden_phrases.extend(_string_list(identity.get("forbidden_generic_phrases") if isinstance(identity, Mapping) else []))
    truncation_markers = _string_list(rules.get("truncation_markers")) or ["...", "…"]

    missing: dict[str, list[str]] = {}
    under_long: list[str] = []
    under_card: list[str] = []
    overflow_card: list[str] = []
    over_long: list[str] = []
    unanchored: list[str] = []
    panel_texts: list[tuple[str, str]] = []
    paragraphs: list[str] = []
    long_counts: list[int] = []
    card_counts: list[int] = []
    scene_setting_hits = 0
    connective_hits = 0
    emotional_hits = 0
    inner_applicable = 0
    inner_hits = 0
    generic_phrase_hits: list[str] = []
    stage_direction_hits: list[str] = []
    silent_truncation_count = 0

    for index, panel in enumerate(panels, start=1):
        panel_id = str(panel.get("panel_id") or f"P{index:02d}")
        metrics = panel_text_metrics(panel)
        long_counts.append(metrics["long_form_chars"])
        card_counts.append(metrics["card_form_chars"])
        paragraphs.extend(panel_long_form_lines(panel))
        paragraphs.extend(panel_card_form_lines(panel))

        panel_missing = []
        if _has_text(panel, "scene_setting"):
            scene_setting_hits += 1
        else:
            panel_missing.append("scene_setting")
        if _has_text(panel, "connective_prose") or _has_text(panel, "narration"):
            connective_hits += 1
        else:
            panel_missing.append("connective_prose")
        if _has_text(panel, "interior_monologue") or _has_text(panel, "emotion"):
            emotional_hits += 1
        else:
            panel_missing.append("emotional_text")

        requirements = panel.get("text_requirements")
        if isinstance(requirements, Mapping) and requirements.get("inner_monologue_applicable"):
            inner_applicable += 1
            if _has_text(panel, "interior_monologue"):
                inner_hits += 1
            else:
                panel_missing.append("interior_monologue")

        panel_lines = [*panel_long_form_lines(panel), *panel_card_form_lines(panel)]
        panel_text = "\n".join(panel_lines)
        # Scan the lines the composer will actually render, not the raw variants:
        # normalize_story_panel_for_package promotes text_layers fields
        # (scene_setting, reality_mapping, ...) into the package panel, and the
        # long-form fallback renders them — a stage direction hiding in
        # text_layers.scene_setting reaches readers even when text_variants is
        # clean (the 大远景 escape, 2026-07-08).
        rendered_panel = normalize_story_panel_for_package(panel)
        rendered_lines = [*panel_long_form_lines(rendered_panel), *panel_card_form_lines(rendered_panel)]
        seen_stage_lines: set[str] = set()
        for raw_line in rendered_lines:
            for line in str(raw_line).splitlines():
                stripped = line.strip()
                if stripped in seen_stage_lines:
                    continue
                if _STAGE_DIRECTION_RE.match(stripped):
                    seen_stage_lines.add(stripped)
                    stage_direction_hits.append(f"{panel_id}:{stripped[:24]}")
        for phrase in forbidden_phrases:
            if phrase and phrase in panel_text:
                generic_phrase_hits.append(f"{panel_id}:{phrase}")
        if any(marker and marker in panel_text for marker in truncation_markers):
            silent_truncation_count += 1
        panel_texts.append((panel_id, panel_text))

        # Caption must touch something actually drawn in its own panel. Panels
        # that declare no staging fields are skipped rather than guessed at.
        staging_terms = _anchor_bigrams(_panel_staging_text(panel))
        if staging_terms and not (staging_terms & _anchor_bigrams(panel_text)):
            unanchored.append(panel_id)

        # Per-panel floor is a low "not empty" guard; the average target is
        # enforced separately below. Otherwise a legitimately terse B-tier beat
        # (征兵吏只说按名应征) would fail just for being short.
        if metrics["long_form_chars"] < PER_PANEL_MIN_CHARS:
            under_long.append(panel_id)
        if metrics["card_form_chars"] < PER_PANEL_CARD_MIN_CHARS:
            under_card.append(panel_id)
        if metrics["card_form_chars"] > card_max_chars or metrics["card_form_paragraphs"] > 3:
            overflow_card.append(panel_id)
        # Cap the upper drift: a caption longer than the max is water-filling.
        if metrics["long_form_chars"] > long_max_chars:
            over_long.append(panel_id)
        if panel_missing:
            missing[panel_id] = panel_missing

    panel_count = len(panels)
    metrics_report = {
        "panel_count": panel_count,
        "avg_long_chars": round(sum(long_counts) / panel_count, 2) if panel_count else 0,
        "avg_card_chars": round(sum(card_counts) / panel_count, 2) if panel_count else 0,
        "scene_setting_coverage": round(scene_setting_hits / panel_count, 4) if panel_count else 0,
        "connective_coverage": round(connective_hits / panel_count, 4) if panel_count else 0,
        "emotional_coverage": round(emotional_hits / panel_count, 4) if panel_count else 0,
        "inner_monologue_applicable_coverage": round(inner_hits / inner_applicable, 4) if inner_applicable else 1.0,
        "card_form_overflow_rate": round(len(overflow_card) / panel_count, 4) if panel_count else 0,
    }
    duplicate_paragraphs = [
        text for text, count in Counter(item for item in paragraphs if len(item) >= 8).items() if count > 1
    ]
    cross_panel_repeats = _cross_panel_phrase_repeats(panel_texts)
    repeated_sentence_pattern_hits = _repeated_pattern_hits(paragraphs)
    near_duplicate_rate = _near_duplicate_rate(paragraphs)
    question_ending_rate = _question_ending_rate(paragraphs)
    memory_sentence_count = sum(1 for item in paragraphs if "记住" in item or "别忘" in item)
    passed = (
        metrics_report["avg_long_chars"] >= thresholds["avg_long_min_chars"]
        and metrics_report["avg_card_chars"] >= thresholds["avg_card_min_chars"]
        and metrics_report["scene_setting_coverage"] >= thresholds["scene_setting_coverage"]
        and metrics_report["connective_coverage"] >= thresholds["connective_coverage"]
        and metrics_report["emotional_coverage"] >= thresholds["emotional_coverage"]
        and metrics_report["inner_monologue_applicable_coverage"] >= thresholds["inner_monologue_applicable_coverage"]
        and metrics_report["card_form_overflow_rate"] <= thresholds["card_form_overflow_rate"]
        and not under_long
        and not under_card
        and not overflow_card
        and not over_long
        and not unanchored
        and not missing
        and not duplicate_paragraphs
        and not cross_panel_repeats
        and not generic_phrase_hits
        and not stage_direction_hits
        and not repeated_sentence_pattern_hits
        and silent_truncation_count == 0
    )
    report = {
        "schema_version": "2.0",
        "updated_at": _now(),
        "passed": passed,
        "thresholds": thresholds,
        "metrics": metrics_report,
        "missing": missing,
        "under_long_form_panels": under_long,
        "under_card_form_panels": under_card,
        "card_form_overflow_panels": overflow_card,
        "over_long_form_panels": over_long,
        "unanchored_panels": unanchored,
        "cross_panel_repeats": cross_panel_repeats,
        "reused_paragraphs": duplicate_paragraphs,
        "exact_duplicate_count": len(duplicate_paragraphs),
        "near_duplicate_rate": round(near_duplicate_rate, 4),
        "generic_phrase_hits": generic_phrase_hits,
        "stage_direction_hits": stage_direction_hits,
        "repeated_sentence_pattern_hits": repeated_sentence_pattern_hits,
        "question_ending_rate": round(question_ending_rate, 4),
        "memory_sentence_count": memory_sentence_count,
        "silent_truncation_count": silent_truncation_count,
    }
    if write_report:
        _write_json(root / "qa" / "text-richness-report.json", report)
    if raise_on_fail and not passed:
        raise ValueError("Text richness validation failed.")
    return report


def validate_lettering_fidelity(
    project: str | Path,
    *,
    raise_on_fail: bool = True,
    write_report: bool = True,
) -> dict[str, Any]:
    root = Path(project)
    episode = _load_episode(root)
    source_chunks = _source_chunk_map(episode, root)
    issues: list[dict[str, str]] = []
    checked: list[dict[str, object]] = []
    for index, panel in enumerate(flatten_episode_panels(episode), start=1):
        if not isinstance(panel, dict):
            continue
        panel_id = str(panel.get("panel_id") or f"P{index:02d}")
        refs = _string_list(panel.get("source_refs"))
        source_text = "\n".join(source_chunks.get(ref, "") for ref in refs if source_chunks.get(ref, "")).strip()
        final_text = "\n".join([*panel_long_form_lines(panel), *panel_card_form_lines(panel)]).strip()
        if not final_text:
            final_text = "\n".join(_string_list(panel.get("narration")) + _string_list(panel.get("dialogue")) + _string_list(panel.get("card_copy")))
        if not source_text or not final_text:
            checked.append({"panel": panel_id, "source_refs": refs, "checked": False, "reason": "missing source or final text"})
            continue
        panel_issues = _fidelity_issues(panel_id, source_text, final_text)
        issues.extend(panel_issues)
        checked.append(
            {
                "panel": panel_id,
                "source_refs": refs,
                "checked": True,
                "source_excerpt": source_text[:220],
                "final_text": final_text[:220],
                "issue_count": len(panel_issues),
            }
        )
    report = {
        "schema_version": "1.0",
        "updated_at": _now(),
        "passed": not issues,
        "checked_panel_count": sum(1 for item in checked if item.get("checked")),
        "issues": issues,
        "checked": checked,
    }
    if write_report:
        _write_json(root / "qa" / "lettering-fidelity-report.json", report)
    if raise_on_fail and issues:
        raise LetteringFidelityError(f"Lettering fidelity failed with {len(issues)} issue(s).", report)
    return report


def _load_episode(root: Path) -> dict[str, Any]:
    return load_episode(root)


def _load_identity_or_empty(root: Path) -> dict[str, Any]:
    try:
        return load_narrative_identity(root)
    except (FileNotFoundError, OSError, json.JSONDecodeError, ValueError):
        return {}


def _load_rules() -> dict[str, Any]:
    if not RULES_PATH.exists():
        return {}
    try:
        data = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _source_chunk_map(episode: Mapping[str, Any], root: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    story_ir = episode.get("story_ir")
    if isinstance(story_ir, Mapping):
        chunks = story_ir.get("source_chunks")
        if isinstance(chunks, Sequence) and not isinstance(chunks, (bytes, bytearray, str)):
            for chunk in chunks:
                if isinstance(chunk, Mapping):
                    chunk_id = str(chunk.get("chunk_id") or chunk.get("id") or "").strip()
                    text = str(chunk.get("text_excerpt") or chunk.get("text") or "").strip()
                    if chunk_id and text:
                        result[chunk_id] = text
    path = root / "source" / "source_chunks.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        chunks = data.get("chunks") if isinstance(data, Mapping) else None
        if isinstance(chunks, Sequence) and not isinstance(chunks, (bytes, bytearray, str)):
            for chunk in chunks:
                if isinstance(chunk, Mapping):
                    chunk_id = str(chunk.get("chunk_id") or chunk.get("id") or "").strip()
                    text = str(chunk.get("text_excerpt") or chunk.get("text") or "").strip()
                    if chunk_id and text:
                        result.setdefault(chunk_id, text)
    return result


def _fidelity_issues(panel_id: str, source_text: str, final_text: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    normalized_final = _normalize_text(final_text)
    for token in NEGATION_TOKENS:
        if token in source_text and token not in final_text:
            issues.append(
                {
                    "panel": panel_id,
                    "type": "negation_dropped",
                    "missing_token": token,
                    "source": source_text[:180],
                    "rewritten": final_text[:180],
                }
            )
    source_numbers = set(NUMBER_PATTERN.findall(source_text))
    final_numbers = set(NUMBER_PATTERN.findall(final_text))
    for number in sorted(source_numbers - final_numbers):
        if len(str(number)) >= 1 and _source_number_is_semantic(str(number), normalized_final):
            issues.append(
                {
                    "panel": panel_id,
                    "type": "number_dropped",
                    "missing_token": str(number),
                    "source": source_text[:180],
                    "rewritten": final_text[:180],
                }
            )
    return issues


def _source_number_is_semantic(number: str, normalized_final: str) -> bool:
    if not number:
        return False
    if number in {"一", "一个"} and "一" in normalized_final:
        return False
    return True


def _has_text(panel: Mapping[str, Any], key: str) -> bool:
    value = panel.get(key)
    if isinstance(value, str) and value.strip():
        return True
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)) and any(str(item).strip() for item in value):
        return True
    layers = panel.get("text_layers")
    if isinstance(layers, Mapping):
        layer_value = layers.get(key)
        if isinstance(layer_value, str) and layer_value.strip():
            return True
        if isinstance(layer_value, Sequence) and not isinstance(layer_value, (bytes, bytearray, str)) and any(str(item).strip() for item in layer_value):
            return True
    return False


def _panel_staging_text(panel: Mapping[str, Any]) -> str:
    """Everything concrete that this panel actually draws."""
    parts: list[str] = []
    for key in _ANCHOR_FIELDS:
        value = panel.get(key)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, Mapping):
            # Chinese lives in the values ("PROP-OAR": "横停在右侧船舷"), not the ids.
            parts.extend(str(item) for item in value.values())
        elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
            parts.extend(str(item) for item in value)
    return " ".join(parts)


def _anchor_bigrams(text: str) -> set[str]:
    """Content bigrams: CJK pairs that carry no function word.

    Bigrams (not full words) because there is no tokenizer here. A false match
    only makes the gate MORE permissive, never a false failure — which is the
    right error direction for a guard whose job is catching the extreme case.
    """
    grams: set[str] = set()
    for block in _CJK_BLOCK_RE.findall(text):
        for index in range(len(block) - 1):
            gram = block[index : index + 2]
            if gram[0] in _ANCHOR_STOP_CHARS or gram[1] in _ANCHOR_STOP_CHARS:
                continue
            grams.add(gram)
    return grams


def _repeated_pattern_hits(paragraphs: list[str]) -> list[dict[str, object]]:
    hits: list[dict[str, object]] = []
    for pattern in REPEATED_TEMPLATE_PATTERNS:
        matched = [text for text in paragraphs if pattern.search(text)]
        if len(matched) >= 3:
            hits.append({"pattern": pattern.pattern, "count": len(matched), "examples": matched[:3]})
    return hits


# A recurring 4+ char content phrase across many panels is setup-repetition
# water-filling (the 木兰 "家无长兄" ×3 problem), not legitimate callback.
_CROSS_PANEL_MIN_PHRASE = 4
_CROSS_PANEL_MIN_PANELS = 3


def _cross_panel_phrase_repeats(panel_texts: list[tuple[str, str]]) -> list[dict[str, object]]:
    """Content phrases (>=4 chars) that recur across >=3 different panels.

    Names and single verbs are shorter than the 4-char window or appear in few
    panels, so they slip past; a whole 4-gram like 家无长兄 repeating across a
    third of the episode is the signal we want.
    """
    if len(panel_texts) < _CROSS_PANEL_MIN_PANELS:
        return []
    phrase_panels: dict[str, set[str]] = {}
    for panel_id, text in panel_texts:
        compact = "".join(ch for ch in text if _is_cjk(ch))
        seen_here: set[str] = set()
        for i in range(len(compact) - _CROSS_PANEL_MIN_PHRASE + 1):
            gram = compact[i : i + _CROSS_PANEL_MIN_PHRASE]
            if gram in seen_here:
                continue
            seen_here.add(gram)
            phrase_panels.setdefault(gram, set()).add(panel_id)
    # Grow each recurring 4-gram rightward as far as it keeps recurring, then keep
    # only maximal phrases, so 十二卷军 / 二卷军书 collapse into one 十二卷军书 report.
    candidates = {g: p for g, p in phrase_panels.items() if len(p) >= _CROSS_PANEL_MIN_PANELS}
    maximal: list[str] = []
    for gram in sorted(candidates, key=len, reverse=True):
        if not any(gram in longer for longer in maximal):
            maximal.append(gram)
    return [{"phrase": g, "panels": sorted(candidates[g])} for g in maximal]


def _is_cjk(ch: str) -> bool:
    return "一" <= ch <= "鿿"


def _near_duplicate_rate(paragraphs: list[str]) -> float:
    normalized = [_normalize_text(item) for item in paragraphs if len(_normalize_text(item)) >= 8]
    if len(normalized) < 2:
        return 0.0
    comparisons = 0
    near = 0
    for left_index in range(len(normalized)):
        for right_index in range(left_index + 1, len(normalized)):
            comparisons += 1
            if _jaccard(_char_ngrams(normalized[left_index]), _char_ngrams(normalized[right_index])) >= 0.78:
                near += 1
    return near / comparisons if comparisons else 0.0


def _question_ending_rate(paragraphs: list[str]) -> float:
    if not paragraphs:
        return 0.0
    return sum(1 for item in paragraphs if item.rstrip().endswith(("?", "？"))) / len(paragraphs)


def _normalize_text(text: str) -> str:
    return re.sub(r"[\s，。！？；：、,.!?;:「」《》“”\"'()（）\[\]【】]+", "", text)


def _char_ngrams(text: str, n: int = 3) -> set[str]:
    if len(text) < n:
        return {text} if text else set()
    return {text[index : index + n] for index in range(len(text) - n + 1)}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
