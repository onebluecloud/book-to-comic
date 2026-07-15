from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
import re
from pathlib import Path
from typing import Any

from .narrative_identity import load_narrative_identity, narrative_identity_summary
from .project_layout import load_episode
from .story_gate import flatten_episode_panels
from .text_bible import panel_card_form_lines, panel_long_form_lines


PASS_THRESHOLD = 0.55
WARN_THRESHOLD = 0.70
PANEL_PHRASE_OVERLAP_FAIL = 0.20


class TextDistinctivenessError(ValueError):
    """Raised when project lettering is too close to generic or prior-project copy."""


def validate_text_distinctiveness(
    project: str | Path,
    *,
    against: list[str] | tuple[str, ...] | None = None,
    raise_on_fail: bool = True,
    write_report: bool = True,
) -> dict[str, Any]:
    root = Path(project)
    current = _project_corpus(root)
    baselines = [_project_corpus(Path(item)) for item in against or []]
    forbidden_hits = _forbidden_hits(current)
    comparisons = [_compare(current, baseline) for baseline in baselines]
    highest_similarity = max((item["similarity"] for item in comparisons), default=0.0)
    max_phrase_overlap = max((item["panel_phrase_overlap"] for item in comparisons), default=0.0)
    direct_fail = bool(forbidden_hits) or max_phrase_overlap >= PANEL_PHRASE_OVERLAP_FAIL

    if direct_fail or highest_similarity > WARN_THRESHOLD:
        status = "failed"
    elif highest_similarity >= PASS_THRESHOLD:
        status = "warn"
    else:
        status = "passed"
    passed = status != "failed"
    report = {
        "schema_version": "2.0",
        "updated_at": _now(),
        "passed": passed,
        "status": status,
        "thresholds": {
            "pass_below": PASS_THRESHOLD,
            "warn_from": PASS_THRESHOLD,
            "fail_above": WARN_THRESHOLD,
            "panel_phrase_overlap_fail": PANEL_PHRASE_OVERLAP_FAIL,
        },
        "current": {
            "project": str(root),
            "paragraph_count": len(current["paragraphs"]),
            "forbidden_phrase_count": len(current["forbidden_phrases"]),
        },
        "forbidden_phrase_hits": forbidden_hits,
        "highest_similarity": round(highest_similarity, 4),
        "max_panel_phrase_overlap": round(max_phrase_overlap, 4),
        "comparisons": comparisons,
    }
    if write_report:
        _write_json(root / "qa" / "text-distinctiveness-report.json", report)
    if raise_on_fail and not passed:
        raise TextDistinctivenessError("Text distinctiveness validation failed.")
    return report


def _project_corpus(root: Path) -> dict[str, Any]:
    identity = _load_identity(root)
    episode = _load_episode(root)
    panels = [panel for panel in flatten_episode_panels(episode) if isinstance(panel, dict)]
    paragraphs: list[str] = []
    for panel in panels:
        paragraphs.extend(panel_long_form_lines(panel))
        paragraphs.extend(panel_card_form_lines(panel))
    summary = narrative_identity_summary(identity) if identity else {}
    identity_text = " ".join(str(value) for value in summary.values() if str(value).strip())
    forbidden = []
    for key in ("forbidden_generic_phrases", "forbidden_cross_book_phrases"):
        forbidden.extend(_string_list(identity.get(key) if isinstance(identity, Mapping) else []))
    return {
        "root": str(root),
        "identity_text": identity_text,
        "paragraphs": _dedupe(paragraphs),
        "text": "\n".join(_dedupe(paragraphs)),
        "tokens": _tokens(identity_text + "\n" + "\n".join(paragraphs)),
        "forbidden_phrases": _dedupe(forbidden),
    }


def _compare(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    token_similarity = _jaccard(set(current["tokens"]), set(baseline["tokens"]))
    phrase_overlap = _paragraph_overlap(current["paragraphs"], baseline["paragraphs"])
    panel_phrase_overlap = _ngram_overlap(current["text"], baseline["text"])
    similarity = token_similarity * 0.45 + phrase_overlap * 0.35 + panel_phrase_overlap * 0.20
    return {
        "against": baseline["root"],
        "similarity": round(similarity, 4),
        "token_similarity": round(token_similarity, 4),
        "paragraph_overlap": round(phrase_overlap, 4),
        "panel_phrase_overlap": round(panel_phrase_overlap, 4),
    }


def _forbidden_hits(corpus: dict[str, Any]) -> list[str]:
    text = corpus["text"]
    return [phrase for phrase in corpus["forbidden_phrases"] if phrase and phrase in text]


def _paragraph_overlap(current: list[str], baseline: list[str]) -> float:
    if not current or not baseline:
        return 0.0
    current_set = {item for item in current if len(item) >= 8}
    baseline_set = {item for item in baseline if len(item) >= 8}
    return _jaccard(current_set, baseline_set)


def _ngram_overlap(current: str, baseline: str, n: int = 4) -> float:
    current_grams = _char_ngrams(current, n)
    baseline_grams = _char_ngrams(baseline, n)
    return _jaccard(current_grams, baseline_grams)


def _char_ngrams(text: str, n: int) -> set[str]:
    compact = re.sub(r"\s+", "", text)
    return {compact[index : index + n] for index in range(0, max(0, len(compact) - n + 1)) if compact[index : index + n].strip()}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _tokens(text: str) -> list[str]:
    return [item for item in re.split(r"[\s，。！？；：、,.!?;:「」《》“”\"'()（）\[\]【】]+", text) if item]


def _load_identity(root: Path) -> dict[str, Any]:
    try:
        return load_narrative_identity(root)
    except (FileNotFoundError, OSError, json.JSONDecodeError, ValueError):
        return {}


def _load_episode(root: Path) -> dict[str, Any]:
    return load_episode(root)


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
