from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


REQUIRED_APPEAL_CHECKS = (
    "three_second_focus",
    "emotion_anchor",
    "character_appeal",
    "memory_sentence",
    "scan_test",
)
VALID_STATUSES = {"passed", "warn", "fail"}


class AppealGateError(ValueError):
    def __init__(self, message: str, report: dict[str, Any]):
        super().__init__(message)
        self.report = report


def validate_appeal(project: str | Path, *, raise_on_fail: bool = True) -> dict[str, Any]:
    root = Path(project)
    report_path = root / "qa" / "appeal-report.json"
    issues: list[dict[str, str]] = []
    if not report_path.exists():
        report = _missing_report()
        _write_json(report_path, report)
        if raise_on_fail:
            raise AppealGateError("Appeal report is missing.", report)
        return report

    report = _read_json(report_path)
    checks = report.get("checks")
    check_map: dict[str, dict[str, Any]] = {}
    if isinstance(checks, list):
        for item in checks:
            if isinstance(item, dict) and str(item.get("name") or "").strip():
                check_map[str(item["name"]).strip()] = item
    elif isinstance(checks, dict):
        for name, item in checks.items():
            if isinstance(item, dict):
                check_map[str(name)] = {"name": str(name), **item}
    else:
        issues.append({"code": "checks-type", "path": "qa/appeal-report.json.checks", "message": "checks must be a list or object."})

    for name in REQUIRED_APPEAL_CHECKS:
        item = check_map.get(name)
        if item is None:
            issues.append({"code": "missing-check", "path": f"qa/appeal-report.json.checks.{name}", "message": f"{name} is required."})
            continue
        status = str(item.get("status") or "").strip()
        if status not in VALID_STATUSES:
            issues.append({"code": "invalid-status", "path": f"qa/appeal-report.json.checks.{name}.status", "message": "status must be passed, warn, or fail."})
        evidence = item.get("evidence")
        if not _has_evidence(evidence):
            issues.append({"code": "missing-evidence", "path": f"qa/appeal-report.json.checks.{name}.evidence", "message": "evidence must be non-empty and inspectable."})
        if status == "fail":
            issues.append({"code": "appeal-fail", "path": f"qa/appeal-report.json.checks.{name}", "message": f"{name} failed and blocks final composition."})

    # The appeal verdict is host judgment, so its only legal write path is the
    # record-appeal-review command — no stamp, or a stamp whose episode hash
    # went stale, means hand-written or outdated (audit P0-2).
    from .review_record import RECORD_APPEAL_TOOL, check_review_provenance

    for problem in check_review_provenance(report, expected_tool=RECORD_APPEAL_TOOL, project=root):
        issues.append({"code": "appeal-provenance", "path": "qa/appeal-report.json.provenance", "message": problem})

    passed = not issues
    normalized = {
        "schema_version": str(report.get("schema_version") or "1.0"),
        "updated_at": _now(),
        "passed": passed,
        "required_checks": list(REQUIRED_APPEAL_CHECKS),
        "checks": [check_map.get(name, {"name": name, "status": "fail", "evidence": []}) for name in REQUIRED_APPEAL_CHECKS],
        "issues": issues,
    }
    # Normalization must not strip the recorded review identity, or the next
    # validation pass would misread a legally recorded report as hand-written.
    if isinstance(report.get("provenance"), dict):
        normalized["provenance"] = report["provenance"]
    if str(report.get("reviewer_pass_id") or "").strip():
        normalized["reviewer_pass_id"] = str(report["reviewer_pass_id"]).strip()
    _write_json(report_path, normalized)
    if raise_on_fail and not passed:
        raise AppealGateError(f"Appeal validation failed with {len(issues)} issue(s).", normalized)
    return normalized


def _missing_report() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "updated_at": _now(),
        "passed": False,
        "required_checks": list(REQUIRED_APPEAL_CHECKS),
        "checks": [{"name": name, "status": "fail", "evidence": []} for name in REQUIRED_APPEAL_CHECKS],
        "issues": [{"code": "missing-report", "path": "qa/appeal-report.json", "message": "Host appeal review must be completed before final composition."}],
    }


def _has_evidence(value: object) -> bool:
    """Content-bearing evidence only. The old fallback `value is not None`
    accepted false and 0 as evidence (release audit P0-1)."""
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, bool) or isinstance(value, (int, float)):
        return False
    if isinstance(value, list):
        return any(_has_evidence(item) for item in value)
    if isinstance(value, dict):
        return any(_has_evidence(item) for item in value.values())
    return False


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON report must be an object: {path}")
    return data


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
