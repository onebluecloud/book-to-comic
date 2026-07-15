"""The only legal write path for LLM/human review verdicts.

qa/*.json reports are machine-owned, but the story LLM gate and the appeal
report need judgment no deterministic validator can compute. The old rule set
required an approved ``llm_gate`` while forbidding every way of writing one
(2026-07 audit P0-2) — the only way through was hand-editing the report, which is
indistinguishable from forgery. ``record-story-review`` /
``record-appeal-review`` close that loop:

* the reviewer (an independent subagent pass, a separate session, or a human)
  produces a verdict file;
* the record command validates its structure, stamps provenance (tool name,
  UTC time, reviewer kind, current episode content hash) and writes the qa
  report;
* ``validate-story`` / ``validate-appeal`` require the provenance stamp AND a
  fresh hash — a hand-edited report carries no stamp, and a recorded review
  goes stale the moment the episode content changes.

Hand-writing the provenance block stays physically possible on a local
filesystem. The stamp is not cryptographic proof of independence — it makes
honesty the cheap path, staleness detectable, and forgery an explicit act
that SKILL.md forbids, which is the honest ceiling for a local tool.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RECORD_STORY_TOOL = "record-story-review"
RECORD_APPEAL_TOOL = "record-appeal-review"
REVIEWER_KINDS = ("independent-subagent", "separate-session", "human")

REQUIRED_STORY_CHECKS = (
    "中文叠字校对",
    "证据链 source coverage 复核",
    "叙事连续性打乱测试",
    "可画性分镜/气泡预算复核",
    "场景多样性复核",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def episode_sha256(project: str | Path) -> str:
    """Hash of the official episode file only.

    Deliberately narrower than delivery_gate.story_fingerprint (which hashes
    every story/*.json): a balloon-plan tweak between composes must not void a
    story review; a content edit must.
    """
    path = Path(project) / "story" / "episode-001.json"
    if not path.is_file():
        raise FileNotFoundError(f"Official episode file is missing: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


PASSING_CHECK_STATUSES = {"passed", "approved"}
EVIDENCE_REQUIRED_KEYS = ("source_excerpt", "final_text", "verdict")


def _complete_evidence(value: object) -> bool:
    """True only for evidence carrying the FULL source_excerpt -> final_text ->
    verdict chain.

    The first cut accepted any item with any one of those keys, so a bare
    {"verdict": "ok"} passed as a complete audit trail (2026-07 release audit
    P0-1). All three must be non-empty strings on at least one item.
    """
    items: list[object]
    if isinstance(value, list):
        items = value
    elif isinstance(value, dict):
        items = [value]
    else:
        return False
    for item in items:
        if isinstance(item, dict) and all(
            isinstance(item.get(key), str) and item[key].strip() for key in EVIDENCE_REQUIRED_KEYS
        ):
            return True
    return False


def validate_review_checks(
    checks: list[dict[str, Any]],
    *,
    required_names: tuple[str, ...],
    require_pass: bool,
) -> list[str]:
    """Shared per-check discipline for story/appeal reviews.

    An overall approval means EVERY required check appeared exactly once,
    passed, and carries the full evidence chain — five failed checks used to
    coexist with llm_gate.status=approved (release audit P0-1).
    """
    problems: list[str] = []
    counts: dict[str, int] = {}
    by_name: dict[str, dict[str, Any]] = {}
    for check in checks:
        name = str(check.get("name") or "").strip()
        counts[name] = counts.get(name, 0) + 1
        by_name[name] = check
    for name in required_names:
        count = counts.get(name, 0)
        if count == 0:
            problems.append(f"required check missing: {name}")
            continue
        if count > 1:
            problems.append(f"required check appears {count} times (must be exactly once): {name}")
            continue
        check = by_name[name]
        status = str(check.get("status") or "").strip().lower()
        if require_pass and status not in PASSING_CHECK_STATUSES:
            problems.append(
                f"check {name!r} has status {status or 'missing'!r}: an approved review requires every "
                "required check to be passed/approved — failed/warn/unknown checks block approval."
            )
        if require_pass and not _complete_evidence(check.get("evidence")):
            problems.append(
                f"check {name!r} lacks complete evidence: at least one item with non-empty "
                "source_excerpt, final_text AND verdict is required."
            )
    return problems


def _load_checks(evidence_file: str | Path) -> list[dict[str, Any]]:
    path = Path(evidence_file)
    data = json.loads(path.read_text(encoding="utf-8"))
    checks = data.get("checks") if isinstance(data, dict) else data
    if not isinstance(checks, list) or not checks:
        raise ValueError(f"{path}: expected a non-empty checks array (either top-level or under 'checks').")
    parsed: list[dict[str, Any]] = []
    for index, check in enumerate(checks):
        if not isinstance(check, dict) or not str(check.get("name") or "").strip():
            raise ValueError(f"{path}: checks[{index}] must be an object with a name.")
        parsed.append(check)
    return parsed


def _provenance(tool: str, root: Path, *, reviewer_kind: str, notes: str) -> dict[str, Any]:
    if reviewer_kind not in REVIEWER_KINDS:
        raise ValueError(f"reviewer_kind must be one of {', '.join(REVIEWER_KINDS)}.")
    stamp: dict[str, Any] = {
        "recorded_by": tool,
        "recorded_at": _now(),
        "reviewer_kind": reviewer_kind,
        "episode_sha256": episode_sha256(root),
    }
    if notes.strip():
        stamp["notes"] = notes.strip()
    return stamp


def record_story_review(
    project: str | Path,
    *,
    author_pass_id: str,
    reviewer_pass_id: str,
    reviewer_kind: str,
    evidence_file: str | Path,
    status: str = "approved",
    notes: str = "",
) -> dict[str, Any]:
    """Write the story LLM gate verdict, then re-run the deterministic gate."""
    root = Path(project)
    author = author_pass_id.strip()
    reviewer = reviewer_pass_id.strip()
    if not author or not reviewer:
        raise ValueError("author_pass_id and reviewer_pass_id are both required.")
    if author == reviewer:
        raise ValueError(
            "reviewer_pass_id must differ from author_pass_id: the writing pass cannot approve itself. "
            "Run the review as an independent subagent, a separate session, or a human."
        )
    if status not in {"approved", "rejected"}:
        raise ValueError("status must be approved or rejected.")
    checks = _load_checks(evidence_file)
    if status == "approved":
        problems = validate_review_checks(checks, required_names=REQUIRED_STORY_CHECKS, require_pass=True)
        if problems:
            raise ValueError("Story review cannot be recorded as approved: " + "; ".join(problems))
    llm_gate: dict[str, Any] = {
        "status": status,
        "author_pass_id": author,
        "reviewer_pass_id": reviewer,
        "checks": checks,
        "issues": [],
        "provenance": _provenance(RECORD_STORY_TOOL, root, reviewer_kind=reviewer_kind, notes=notes),
    }
    report_path = root / "qa" / "story-gate-report.json"
    report: dict[str, Any] = {}
    if report_path.is_file():
        try:
            loaded = json.loads(report_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                report = loaded
        except (OSError, json.JSONDecodeError):
            report = {}
    report["llm_gate"] = llm_gate
    report["updated_at"] = _now()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Re-run the deterministic gate so the report on disk is a full, coherent
    # verdict (it inherits the llm_gate block we just recorded). Deterministic
    # failures don't undo the recording — the report carries them.
    from .story_gate import StoryGateError, validate_story_gate

    try:
        return validate_story_gate(root, require_llm_gate=status == "approved")
    except StoryGateError as exc:
        return exc.report


def approved_panels_sha256(project: str | Path) -> str:
    """Fingerprint of the approved panel set (index + content hash, sorted).

    Appeal is a VISUAL review; binding it only to the episode JSON meant a
    swapped panel image kept its old appeal verdict (release audit P0-1.5).

    The fingerprint hashes the ACTUAL canonical file bytes, not just the
    manifest's declared sha — hashing declarations alone meant swapping
    assets/panels/NN.png for another valid PNG kept every stamp green
    (release audit v5.13.1 P0-2). A missing canonical file or a
    declared/actual mismatch changes the fingerprint too, so stale stamps
    fail closed instead of validating a lie. Empty string when no approved
    panels exist.
    """
    root = Path(project)
    manifest_path = root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        return ""
    entries = []
    for item in manifest.get("assets", []):
        if not (isinstance(item, dict) and item.get("kind") == "panel" and item.get("status") == "approved"):
            continue
        declared = str(item.get("canonical_sha256") or "")
        canonical = root / str(item.get("canonical_path") or "")
        try:
            actual = hashlib.sha256(canonical.read_bytes()).hexdigest()
        except (FileNotFoundError, OSError):
            actual = "MISSING"
        entries.append((int(item.get("panel_index") or 0), declared, actual))
    if not entries:
        return ""
    digest = hashlib.sha256()
    for index, declared, actual in sorted(entries):
        digest.update(f"{index}:{declared}:{actual};".encode("utf-8"))
    return digest.hexdigest()


APPEAL_CHECK_STATUSES = {"passed", "warn", "fail"}


def record_appeal_review(
    project: str | Path,
    *,
    reviewer_pass_id: str,
    reviewer_kind: str,
    checks_file: str | Path,
    notes: str = "",
) -> dict[str, Any]:
    """Write the appeal (感染力) review, then re-run validate-appeal."""
    from .appeal import REQUIRED_APPEAL_CHECKS, validate_appeal

    root = Path(project)
    reviewer = reviewer_pass_id.strip()
    if not reviewer:
        raise ValueError("reviewer_pass_id is required.")
    checks = _load_checks(checks_file)
    problems: list[str] = []
    counts: dict[str, int] = {}
    for check in checks:
        name = str(check.get("name") or "").strip()
        counts[name] = counts.get(name, 0) + 1
        status = str(check.get("status") or "").strip().lower()
        if status not in APPEAL_CHECK_STATUSES:
            problems.append(f"check {name!r} has invalid status {status!r} (must be passed/warn/fail).")
        if not _content_evidence(check.get("evidence")):
            problems.append(
                f"check {name!r} has no usable evidence: booleans, numbers and empty containers do not count."
            )
    for name in REQUIRED_APPEAL_CHECKS:
        if counts.get(name, 0) != 1:
            problems.append(f"required appeal check must appear exactly once: {name} (found {counts.get(name, 0)}).")
    if problems:
        raise ValueError("Appeal review cannot be recorded: " + "; ".join(problems))
    panels_fingerprint = approved_panels_sha256(root)
    if not panels_fingerprint:
        raise ValueError(
            "Appeal review needs approved panels to look at: no approved panel assets found in manifest.json. "
            "Approve the artwork first, then record the appeal review."
        )
    provenance = _provenance(RECORD_APPEAL_TOOL, root, reviewer_kind=reviewer_kind, notes=notes)
    provenance["approved_panels_sha256"] = panels_fingerprint
    report = {
        "schema_version": "1.0",
        "updated_at": _now(),
        "reviewer_pass_id": reviewer,
        "checks": checks,
        "provenance": provenance,
    }
    report_path = root / "qa" / "appeal-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return validate_appeal(root, raise_on_fail=False)


def _content_evidence(value: object) -> bool:
    """Evidence must carry actual content: non-empty strings, or containers
    that contain one. Booleans/numbers passed the old `is not None` test
    (release audit P0-1: evidence=false counted as evidence)."""
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, bool) or isinstance(value, (int, float)):
        return False
    if isinstance(value, list):
        return any(_content_evidence(item) for item in value)
    if isinstance(value, dict):
        return any(_content_evidence(item) for item in value.values())
    return False


def check_review_provenance(
    report: dict[str, Any],
    *,
    expected_tool: str,
    project: str | Path,
) -> list[str]:
    """Shared freshness/authenticity check for validate-story / validate-appeal.

    Returns human-readable problems (empty list = provenance is present and
    fresh). Kept dependency-free so both gates can call it.
    """
    problems: list[str] = []
    provenance = report.get("provenance")
    if not isinstance(provenance, dict):
        problems.append(
            f"review has no provenance stamp — verdicts must be written via the {expected_tool} command, "
            "not by editing the qa report."
        )
        return problems
    if str(provenance.get("recorded_by") or "") != expected_tool:
        problems.append(
            f"review provenance says recorded_by={provenance.get('recorded_by')!r}, expected {expected_tool!r}."
        )
    if str(provenance.get("reviewer_kind") or "") not in REVIEWER_KINDS:
        problems.append("review provenance is missing a valid reviewer_kind.")
    try:
        current = episode_sha256(project)
    except (FileNotFoundError, OSError):
        current = ""
    recorded = str(provenance.get("episode_sha256") or "")
    if current and recorded != current:
        problems.append(
            "review is stale: the episode content changed after the review was recorded — "
            f"re-run the review and {expected_tool}."
        )
    if expected_tool == RECORD_APPEAL_TOOL:
        # Visual review: swapping an approved panel must void the verdict too.
        current_panels = approved_panels_sha256(project)
        recorded_panels = str(provenance.get("approved_panels_sha256") or "")
        if not recorded_panels:
            problems.append("appeal provenance is missing approved_panels_sha256 — re-record with the current tool.")
        elif current_panels and recorded_panels != current_panels:
            problems.append(
                "appeal review is stale: the approved panel set changed after the review was recorded — "
                "re-inspect the artwork and re-run record-appeal-review."
            )
    return problems
