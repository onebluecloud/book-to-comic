from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


DELIVERY_INTENTS = {"mass_traffic", "hardcore_showcase"}
HARD_BOOK_SIGNALS = (
    "政治秩序",
    "政治",
    "制度",
    "国家",
    "秩序",
    "史",
    "福山",
    "fukuyama",
    "political",
    "order",
    "origins",
    "state",
    "institution",
)


class FitValidationError(ValueError):
    def __init__(self, message: str, report: dict[str, Any]):
        super().__init__(message)
        self.report = report


def validate_fit(project: str | Path, *, raise_on_fail: bool = True) -> dict[str, Any]:
    root = Path(project)
    project_data = _read_json(root / "project.json")
    intent = str(project_data.get("delivery_intent") or "").strip()
    issues: list[dict[str, str]] = []
    if intent not in DELIVERY_INTENTS:
        issues.append(
            {
                "code": "delivery-intent",
                "path": "project.json.delivery_intent",
                "message": "delivery_intent must be mass_traffic or hardcore_showcase.",
            }
        )
    title_blob = _title_blob(root, project_data)
    hard_score = sum(1 for signal in HARD_BOOK_SIGNALS if signal.lower() in title_blob.lower())
    is_hard = hard_score >= 2
    temperature = "cold" if intent == "mass_traffic" and is_hard else "warm"
    status = "warn" if temperature == "cold" else "passed"
    recommendation = (
        "此书制度史/思想史属性强，引流场景下偏冷；建议改 hardcore_showcase，或增加人物命运线与生活桥。"
        if status == "warn"
        else "当前 delivery_intent 与选题温度基本匹配。"
    )
    report = {
        "schema_version": "1.0",
        "updated_at": _now(),
        "passed": not issues,
        "status": "fail" if issues else status,
        "delivery_intent": intent,
        "temperature_estimate": temperature,
        "hard_book_signal_count": hard_score,
        "recommendation": recommendation,
        "issues": issues,
    }
    _write_json(root / "qa" / "fit-report.json", report)
    if raise_on_fail and issues:
        raise FitValidationError("Fit validation failed.", report)
    return report


def _title_blob(root: Path, project: dict[str, Any]) -> str:
    parts = [str(project.get("book_title") or ""), str(project.get("project_title") or "")]
    for relative in ("story/episode-001.json", "source/metadata.json", "planning/visual_identity.json"):
        path = root / relative
        if path.exists():
            try:
                parts.append(json.dumps(_read_json(path), ensure_ascii=False))
            except (OSError, ValueError, json.JSONDecodeError):
                pass
    return "\n".join(parts)


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON file must be an object: {path}")
    return data


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
