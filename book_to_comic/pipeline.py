from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable

from .appeal import validate_appeal
from .argument_map import validate_argument_map
from .artifact_materializer import (
    _is_schema3_project,
    compose_artifact_project,
    formal_compose_gates,
    validate_project_assets,
)
from .source_claims import validate_source_claims
from .character_qa import validate_character_design
from .conflict_gate import validate_conflict
from .delivery_config import validate_panel_aspect_consistency
from .delivery_gate import validate_delivery
from .grounding_qa import validate_grounding
from .fit import validate_fit
from .lettering_qa import validate_lettering_layout
from .narrative_identity import validate_narrative_identity
from .page_qa import validate_page_plan
from .source_fidelity import validate_source_fidelity
from .story_gate import validate_story_gate
from .text_distinctiveness import validate_text_distinctiveness
from .text_qa import validate_lettering_fidelity, validate_text_richness
from .visual_contract import build_visual_contract, validate_visual_contract
from .visual_distinctiveness import validate_distinctiveness
from .visual_identity import validate_visual_identity
from .world_qa import validate_world_specificity


STAGES = {"plan", "visual", "text", "compose", "all"}


def run_pipeline(project: str | Path, *, stage: str = "all", resume_panel: int | None = None) -> dict[str, Any]:
    if stage not in STAGES:
        raise ValueError("stage must be one of plan, visual, text, compose, all")
    root = Path(project)
    selected = ("plan", "visual", "text", "compose") if stage == "all" else (stage,)
    results: list[dict[str, Any]] = []

    def _stage_blocked() -> bool:
        # Fail fast ACROSS stages too: a failed plan used to fall through to
        # visual/text/compose and exit 0 (release audit P0-3).
        return any(step["status"] in {"failed", "host_action_required"} for step in results)

    for item in selected:
        if _stage_blocked():
            break
        if item == "plan":
            results.extend(_run_steps(root, (
                ("validate-grounding", lambda: validate_grounding(root, require_profile=True)),
                ("validate-fit", lambda: validate_fit(root)),
                ("validate-argument-map", lambda: validate_argument_map(root)),
                ("validate-source-fidelity", lambda: validate_source_fidelity(root)),
                ("validate-character-design", lambda: validate_character_design(root)),
                ("validate-world-specificity", lambda: validate_world_specificity(root)),
                ("validate-conflict", lambda: validate_conflict(root)),
                ("validate-story", lambda: validate_story_gate(root)),
                ("validate-page-plan", lambda: validate_page_plan(root)),
            )))
        elif item == "visual":
            results.extend(_run_steps(root, (
                ("validate-visual-identity", lambda: validate_visual_identity(root)),
                ("validate-distinctiveness", lambda: validate_distinctiveness(root)),
                ("build-visual-contract", lambda: build_visual_contract(root)),
                ("validate-visual-contract", lambda: validate_visual_contract(root)),
            )))
            try:
                report = validate_project_assets(root)
                results.append({"step": "validate-project-assets", "status": "passed", "summary": f"{report['panel_count']} approved panel(s)"})
            except Exception as exc:  # noqa: BLE001 - pipeline records host stop points.
                panel_text = f" panel {resume_panel:02d}" if resume_panel else ""
                results.append({"step": "host-image-assets", "status": "host_action_required", "summary": f"Generate/materialize/approve missing{panel_text} panel assets: {exc}"})
                if stage == "visual":
                    break
        elif item == "text":
            results.extend(_run_steps(root, (
                ("validate-narrative-identity", lambda: validate_narrative_identity(root)),
                ("validate-text-richness", lambda: validate_text_richness(root)),
                ("validate-lettering-fidelity", lambda: validate_lettering_fidelity(root)),
                ("validate-text-distinctiveness", lambda: validate_text_distinctiveness(root)),
                ("validate-lettering-layout", lambda: validate_lettering_layout(root)),
                ("validate-appeal", lambda: validate_appeal(root)),
            )))
        elif item == "compose":
            # compose_artifact_project already builds covers and stamps the
            # delivery gate over the finished final/. Re-running build-cover
            # here mutated final/cover AFTER the stamp, so the recommended
            # one-shot path exited 0 while validate-delivery failed (release
            # audit v5.13.1 P0-1). Instead, the LAST compose step re-verifies
            # the stamp so "pipeline passed" implies "delivery valid".
            results.extend(_run_steps(root, (
                ("compose-project", lambda: compose_artifact_project(root)),
                ("validate-delivery", lambda: validate_delivery(root)),
            )))
    if any(step["status"] == "failed" for step in results):
        overall = "failed"
    elif any(step["status"] == "host_action_required" for step in results):
        overall = "host_action_required"
    else:
        overall = "passed"
    report = {
        "schema_version": "1.1",
        "updated_at": _now(),
        "stage": stage,
        "resume_panel": resume_panel,
        "overall_status": overall,
        "all_passed": overall == "passed",
        "steps": results,
    }
    _write_json(root / "qa" / "pipeline-report.json", report)
    return report


CHECK_STAGES = {"plan", "visual", "text", "assets", "all"}


def check_project(project: str | Path, *, stage: str = "all") -> dict[str, Any]:
    """Run every deterministic gate that compose-project will run, without
    building or composing anything.

    Unlike run-pipeline this never stops at the first failure: it runs them all
    and returns one pass/fail summary, so the host can fix everything in one go
    instead of discovering failures one command at a time.
    """
    if stage not in CHECK_STAGES:
        raise ValueError("stage must be one of plan, visual, text, assets, all")
    root = Path(project)
    # THE registry: check runs exactly what compose-project will require (same
    # function, no hand-maintained copy — audit R2 P1-5), plus a few
    # check-only authoring extras that compose does not re-run.
    is_v3 = _is_schema3_project(root)
    # check and compose must share ONE panel-count contract, computed from the
    # official episode — check used to omit it while compose passed the asset
    # count, so a story/asset mismatch surfaced only at compose (release audit
    # v5.13.2 P1-5).
    expected_panel_count: int | None = None
    try:
        from .project_layout import load_episode
        from .story_gate import flatten_episode_panels

        expected_panel_count = len(flatten_episode_panels(load_episode(root))) or None
    except Exception:  # noqa: BLE001 - a broken episode fails its own gate below.
        expected_panel_count = None
    registry = formal_compose_gates(root, schema3=is_v3, expected_panel_count=expected_panel_count)
    grouped: dict[str, list[tuple[str, Callable[[], Any]]]] = {"plan": [], "visual": [], "text": [], "assets": []}
    for gate_stage, name, thunk in registry:
        grouped[gate_stage].append((name, thunk))
    # Check-only extras (upstream authoring gates + delivery freshness):
    grouped["visual"] += [
        ("validate-visual-identity", lambda: validate_visual_identity(root)),
        ("validate-distinctiveness", lambda: validate_distinctiveness(root)),
    ]
    grouped["assets"] = [
        ("validate-project-assets", lambda: validate_project_assets(root)),
        *grouped["assets"],
        ("validate-delivery", lambda: validate_delivery(root)),
    ]
    groups: dict[str, tuple[tuple[str, Callable[[], Any]], ...]] = {
        key: tuple(value) for key, value in grouped.items()
    }
    selected = ("plan", "visual", "text", "assets") if stage == "all" else (stage,)
    checks: list[dict[str, Any]] = []
    for st in selected:
        for name, fn in groups.get(st, ()):
            try:
                fn()
                checks.append({"check": name, "stage": st, "status": "passed"})
            except Exception as exc:  # noqa: BLE001 - report every failure, never stop early.
                checks.append({"check": name, "stage": st, "status": "failed", "reason": str(exc)})
    failed = [item for item in checks if item["status"] == "failed"]
    report = {
        "schema_version": "1.0",
        "updated_at": _now(),
        "stage": stage,
        "passed_count": len(checks) - len(failed),
        "failed_count": len(failed),
        "all_passed": not failed,
        "checks": checks,
    }
    _write_json(root / "qa" / "check-report.json", report)
    return report


def _run_steps(root: Path, steps: tuple[tuple[str, Callable[[], Any]], ...]) -> list[dict[str, Any]]:
    results = []
    for name, fn in steps:
        try:
            result = fn()
            results.append({"step": name, "status": "passed", "summary": _summary(result)})
        except Exception as exc:  # noqa: BLE001 - callers need a resumable report, not first exception.
            results.append({"step": name, "status": "failed", "summary": str(exc)})
            break
    return results


def _summary(value: object) -> str:
    if isinstance(value, dict):
        if "passed" in value:
            return f"passed={value.get('passed')}"
        if "panel_count" in value:
            return f"panel_count={value.get('panel_count')}"
        if "status" in value:
            return f"status={value.get('status')}"
    return "ok"


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
