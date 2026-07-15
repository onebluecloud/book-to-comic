from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .visual_identity import SCHEMA_VERSION, load_visual_identity, validate_visual_identity


PASS_BELOW = 0.55
WARN_AT = 0.55
FAIL_ABOVE = 0.70

WEIGHTS = {
    "adaptation_viewpoint_cast": 0.20,
    "role_architecture": 0.15,
    "character_shape_wardrobe": 0.15,
    "environment_system": 0.20,
    "motif_props": 0.10,
    "palette_lighting": 0.10,
    "camera_opening": 0.10,
    "style_id": 0.00,
}


class DistinctivenessError(ValueError):
    """Raised when a project's visual identity is too similar to another project."""


def validate_distinctiveness(
    project: str | Path,
    *,
    against: Iterable[str | Path] | None = None,
    raise_on_fail: bool = True,
    write_report: bool = True,
) -> dict[str, Any]:
    root = Path(project)
    validate_visual_identity(root)
    current = load_visual_identity(root)

    baselines = [Path(item) for item in against] if against is not None else _discover_baselines(root)
    baselines = [path for path in baselines if path.resolve() != root.resolve()]

    if not baselines:
        report = {
            "schema_version": SCHEMA_VERSION,
            "updated_at": _now(),
            "project": str(root),
            "passed": True,
            "status": "no_baseline",
            "highest_similarity": 0.0,
            "thresholds": {"pass_below": PASS_BELOW, "warn_at": WARN_AT, "fail_above": FAIL_ABOVE},
            "weighted_scores": {key: 0.0 for key in WEIGHTS},
            "compared_projects": [],
            "comparisons": [],
            "collisions": [],
            "required_revisions": [],
        }
        if write_report:
            _write_json(root / "qa" / "distinctiveness-report.json", report)
        return report

    comparisons: list[dict[str, Any]] = []
    for baseline in baselines:
        validate_visual_identity(baseline)
        previous = load_visual_identity(baseline)
        comparisons.append(_compare_identity(current, previous, baseline))

    worst = max(comparisons, key=lambda item: float(item["similarity"]))
    highest = float(worst["similarity"])
    direct_fail = any(item.get("direct_fail") for item in comparisons)
    if direct_fail or highest > FAIL_ABOVE:
        status = "failed"
    elif highest >= WARN_AT:
        status = "warning"
    else:
        status = "passed"
    passed = status != "failed"
    collisions = [item for comparison in comparisons for item in comparison.get("collisions", [])]
    report = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": _now(),
        "project": str(root),
        "passed": passed,
        "status": status,
        "highest_similarity": round(highest, 4),
        "thresholds": {"pass_below": PASS_BELOW, "warn_at": WARN_AT, "fail_above": FAIL_ABOVE},
        "weighted_scores": worst["weighted_scores"],
        "compared_projects": [str(item) for item in baselines],
        "comparisons": comparisons,
        "collisions": collisions,
        "required_revisions": _required_revisions(collisions),
    }
    if write_report:
        _write_json(root / "qa" / "distinctiveness-report.json", report)
    if raise_on_fail and not passed:
        raise DistinctivenessError(
            "Distinctiveness validation failed. "
            f"highest_similarity={report['highest_similarity']}; collisions={len(collisions)}"
        )
    return report


def _compare_identity(current: Mapping[str, Any], previous: Mapping[str, Any], baseline: Path) -> dict[str, Any]:
    scores = {
        "adaptation_viewpoint_cast": _jaccard(
            _field_tokens(current, ("adaptation_form",), ("cast_model", "role_architecture")),
            _field_tokens(previous, ("adaptation_form",), ("cast_model", "role_architecture")),
        ),
        "role_architecture": _jaccard(
            _field_tokens(current, ("cast_model",)),
            _field_tokens(previous, ("cast_model",)),
        ),
        "character_shape_wardrobe": _jaccard(
            _field_tokens(current, ("character_system",)),
            _field_tokens(previous, ("character_system",)),
        ),
        "environment_system": _jaccard(
            _field_tokens(current, ("environment_system",)),
            _field_tokens(previous, ("environment_system",)),
        ),
        "motif_props": _jaccard(
            _field_tokens(current, ("motif_system",), ("camera_composition", "opening_pattern")),
            _field_tokens(previous, ("motif_system",), ("camera_composition", "opening_pattern")),
        ),
        "palette_lighting": _jaccard(
            _field_tokens(current, ("palette_lighting",)),
            _field_tokens(previous, ("palette_lighting",)),
        ),
        "camera_opening": _jaccard(
            _field_tokens(current, ("camera_composition",)),
            _field_tokens(previous, ("camera_composition",)),
        ),
        "style_id": 0.0,
    }
    weighted = sum(scores[key] * WEIGHTS[key] for key in WEIGHTS)
    collisions = _collisions(scores, baseline)
    direct_fail = (
        scores["role_architecture"] >= 0.65
        and scores["environment_system"] >= 0.55
        and (scores["motif_props"] >= 0.55 or scores["camera_opening"] >= 0.55)
    )
    return {
        "against_project": str(baseline),
        "similarity": round(weighted, 4),
        "weighted_scores": {key: round(value, 4) for key, value in scores.items()},
        "direct_fail": direct_fail,
        "collisions": collisions,
    }


def _collisions(scores: Mapping[str, float], baseline: Path) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    thresholds = {
        "adaptation_viewpoint_cast": 0.65,
        "role_architecture": 0.65,
        "character_shape_wardrobe": 0.60,
        "environment_system": 0.55,
        "motif_props": 0.55,
        "palette_lighting": 0.70,
        "camera_opening": 0.55,
    }
    field_labels = {
        "adaptation_viewpoint_cast": "adaptation_form",
        "role_architecture": "role_architecture",
        "character_shape_wardrobe": "character_system",
        "environment_system": "environment_system",
        "motif_props": "motif_or_opening",
        "palette_lighting": "palette_lighting",
        "camera_opening": "motif_or_opening",
    }
    for key, threshold in thresholds.items():
        score = scores.get(key, 0.0)
        if score >= threshold:
            result.append(
                {
                    "against_project": str(baseline),
                    "field": field_labels[key],
                    "score": round(score, 4),
                    "reason": f"{key} similarity is {score:.2f}, above {threshold:.2f}",
                }
            )
    return result


def _required_revisions(collisions: Sequence[Mapping[str, Any]]) -> list[str]:
    revisions: list[str] = []
    fields = {str(item.get("field", "")) for item in collisions}
    if "role_architecture" in fields:
        revisions.append("Change role architecture and relationship engine, not just names.")
    if "character_system" in fields:
        revisions.append("Revise silhouettes, body variation, wardrobe rules and character archetype bans.")
    if "environment_system" in fields:
        revisions.append("Replace dominant environment categories, anchors and recurring layouts.")
    if "motif_or_opening" in fields:
        revisions.append("Replace signature props, symbolic motifs or opening composition pattern.")
    if "palette_lighting" in fields:
        revisions.append("Adjust palette and lighting so style reuse does not become design reuse.")
    return revisions


def _discover_baselines(root: Path) -> list[Path]:
    parent = root.parent
    if not parent.exists():
        return []
    result: list[Path] = []
    for candidate in parent.iterdir():
        if candidate == root or not candidate.is_dir():
            continue
        if (candidate / "planning" / "visual_identity.json").exists():
            result.append(candidate)
    return result


def _field_tokens(identity: Mapping[str, Any], *paths: tuple[str, ...]) -> set[str]:
    tokens: set[str] = set()
    for path in paths:
        tokens.update(_tokens(_get(identity, path)))
    return tokens


def _tokens(value: object) -> set[str]:
    text = _flatten(value).lower()
    words = set(re.findall(r"[a-z0-9][a-z0-9_-]*", text))
    cjk_runs = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    words.update(cjk_runs)
    return {word for word in words if word and word not in _STOPWORDS}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _flatten(value: object) -> str:
    if isinstance(value, Mapping):
        return " ".join(_flatten(value[key]) for key in sorted(value))
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes, bytearray)):
        return " ".join(_flatten(item) for item in value)
    return str(value or "")


def _get(value: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


_STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "by",
    "for",
    "in",
    "into",
    "is",
    "of",
    "on",
    "or",
    "the",
    "this",
    "to",
    "with",
}
