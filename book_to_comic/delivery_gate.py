"""Bind "the gates ran and passed" to "THESE exact deliverables were emitted".

Before this module the two were unrelated: an agent could run
``check --stage visual`` (three gates), call the composer library functions
directly, and end up with a complete ``final/`` deliverable whose text gates had
never run.

The stamp written by ``compose_artifact_project`` now records:

* **outputs** — every file under ``final/`` (except the bundle archives, which
  are written after the stamp so they can carry it) with size + SHA-256;
* **inputs** — fingerprints of everything the deliverable was composed FROM:
  story JSONs, the approved panel set, the grounding/rights profile and
  project.json.

``validate_delivery`` refuses: deliverables with no stamp, forced/failing
stamps, tampered or missing output files, unexpected extra files, changed
story/panels/rights inputs — and re-runs the export-rights decision so a
project whose rights status changed after compose cannot keep presenting an
old public production.zip (2026-07 release audit P0-2: swapping comic.pdf or
deleting every real deliverable used to validate clean). An empty ``final/``
tree (just the directories init pre-creates) is the neutral "not composed
yet" state, not a failure (release audit P0-3).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DELIVERY_GATE_FILENAME = "delivery-gate.json"
BUNDLE_MANIFEST_FILENAME = "bundle-manifest.json"
SCHEMA_VERSION = "2.0"
# Written after the stamp (so bundles can contain it); excluded from the
# output manifest and integrity walk, but bound separately by
# qa/bundle-manifest.json (release audit v5.13.1 P0-2: swapping or deleting
# production.zip used to validate clean).
BUNDLE_NAMES = {"production.zip", "production-private.zip", "production-debug.zip"}
# Revoked bundles are quarantined OUTSIDE final/ so they can never be swept
# into a later public bundle again (release audit v5.13.1 P0-3).
QUARANTINE_DIR = ("quarantine", "revoked-bundles")

# Convergence signal (v5.13.5 field report): a clean delivery-gate pass is the
# END of the episode's work. Without an explicit "you are done" marker the host
# agent kept improving an already-passing comic — re-planning the story and
# re-rendering all panels for a "better" second version, roughly doubling the
# run and then stalling. Every completion surface (stamp, compose return, CLI)
# repeats this one sentence so the agent cannot miss it.
COMPLETION_STATE_DELIVERED = "delivered"
COMPLETION_STATE_FORCED = "forced-review"
COMPLETION_GUIDANCE = (
    "本话已产出通过质检的合格成品——这是终态,停手。不要为了追求'更好'而重规划故事、"
    "重抽画面或重 compose 一个已经过闸的成品;appeal 的 warn 不构成重做理由。合法的后续"
    "只有两个:①用户明确要求修订 ②add-episode 推进下一话。"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _stamp_path(root: Path) -> Path:
    return root / "qa" / DELIVERY_GATE_FILENAME


def _story_dir(root: Path) -> Path:
    return root / "story"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def story_fingerprint(root: Path) -> str:
    """Stable hash of every story JSON that feeds lettering and pacing."""
    story = _story_dir(root)
    if not story.is_dir():
        return ""
    digest = hashlib.sha256()
    for path in sorted(story.glob("*.json")):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _file_sha_or_empty(path: Path) -> str:
    try:
        return _sha256(path)
    except (FileNotFoundError, OSError):
        return ""


def input_fingerprints(root: Path) -> dict[str, str]:
    """Everything the deliverable is composed FROM. Any change voids the stamp."""
    from .review_record import approved_panels_sha256

    return {
        "story_sha256": story_fingerprint(root),
        "approved_panels_sha256": approved_panels_sha256(root),
        "grounding_profile_sha256": _file_sha_or_empty(root / "planning" / "grounding_profile.json"),
        "project_sha256": _file_sha_or_empty(root / "project.json"),
    }


def final_output_files(root: Path) -> list[Path]:
    """Real deliverable FILES under final/ (bundles excluded); empty dirs are
    the neutral not-composed state.

    ``.REVOKED`` files are deliberately NOT excluded any more: silently
    ignoring them let revoked (rights-withdrawn) archives sit in final/ and
    ride into the next public bundle (release audit v5.13.1 P0-3). A revoked
    file that somehow lands in final/ now shows up as an unexpected stray and
    fails validation closed.
    """
    final = root / "final"
    if not final.is_dir():
        return []
    return sorted(
        path
        for path in final.rglob("*")
        if path.is_file() and path.name not in BUNDLE_NAMES
    )


def outputs_manifest(root: Path) -> dict[str, dict[str, Any]]:
    manifest: dict[str, dict[str, Any]] = {}
    for path in final_output_files(root):
        relative = path.relative_to(root).as_posix()
        manifest[relative] = {"size": path.stat().st_size, "sha256": _sha256(path)}
    return manifest


def is_artifact_project(root: str | Path) -> bool:
    """True when the directory is a gated artifact project rather than a demo run."""
    root = Path(root)
    return _story_dir(root).is_dir() and (root / "project.json").is_file()


def stamp_delivery(
    project: str | Path,
    *,
    gates: list[str],
    panel_count: int,
    forced: bool = False,
    forced_reason: str = "",
    rights_status: str = "",
    public_export_allowed: bool | None = None,
    rights_reasons: list[str] | None = None,
    panel_source_modes: list[str] | None = None,
    expected_bundle_name: str = "",
    expected_bundle_tier: str = "",
) -> dict[str, Any]:
    """Record that these exact final/ files were emitted under a known verdict."""
    root = Path(project)
    final = root / "final"
    if final.is_dir():
        dirty = sorted(p.relative_to(root).as_posix() for p in final.rglob("*.REVOKED") if p.is_file())
        if dirty:
            raise ValueError(
                "final/ contains revoked bundle artifacts that must live in quarantine/, not final/: "
                + ", ".join(dirty)
            )
    stamp: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": _now(),
        "passed": not forced,
        "forced": forced,
        "forced_reason": forced_reason if forced else "",
        "gates": sorted(gates),
        "panel_count": panel_count,
        "inputs": input_fingerprints(root),
        "outputs": outputs_manifest(root),
    }
    # Kept top-level for older readers (regeneration audit, existing reports).
    stamp["story_sha256"] = stamp["inputs"]["story_sha256"]
    if expected_bundle_name:
        if expected_bundle_name not in BUNDLE_NAMES:
            raise ValueError(f"expected_bundle_name must be one of {sorted(BUNDLE_NAMES)}: {expected_bundle_name}")
        # A successful compose PROMISES a production archive. Without this
        # promise in the stamp, deleting both the ZIP and its sidecar used to
        # validate clean (release audit v5.13.2 P0-1).
        stamp["expected_bundle_name"] = expected_bundle_name
        stamp["expected_bundle_tier"] = expected_bundle_tier
        stamp["bundle_manifest_required"] = True
    if rights_status:
        stamp["rights_status"] = rights_status
    if public_export_allowed is not None:
        stamp["public_export_allowed"] = public_export_allowed
    if rights_reasons:
        stamp["rights_reasons"] = list(rights_reasons)
    if panel_source_modes:
        stamp["panel_source_modes"] = list(panel_source_modes)
    # Machine-readable convergence marker — series-status and any host that
    # reads the stamp can tell a finished episode from one still in progress
    # (v5.13.5). A forced/bypassed compose is NOT a clean delivery, so it is
    # marked forced-review instead of delivered.
    stamp["completion"] = {
        "state": COMPLETION_STATE_FORCED if forced else COMPLETION_STATE_DELIVERED,
        "guidance": COMPLETION_GUIDANCE,
    }
    qa_dir = root / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    _stamp_path(root).write_text(json.dumps(stamp, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return stamp


def load_delivery_stamp(project: str | Path) -> dict[str, Any] | None:
    path = _stamp_path(Path(project))
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _revoke_public_bundle(root: Path, issues: list[str]) -> None:
    """Quarantine a public bundle whose rights basis no longer holds.

    The revoked archive is moved OUT of final/ into
    quarantine/revoked-bundles/ — leaving it in final/ (even renamed) let the
    next public compose sweep it back into production.zip (release audit
    v5.13.1 P0-3).
    """
    bundle = root / "final" / "production.zip"
    if not bundle.is_file():
        return
    quarantine = root.joinpath(*QUARANTINE_DIR)
    quarantine.mkdir(parents=True, exist_ok=True)
    revoked = quarantine / f"production.zip.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.REVOKED"
    counter = 1
    while revoked.exists():
        revoked = quarantine / f"production.zip.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.{counter}.REVOKED"
        counter += 1
    try:
        bundle.rename(revoked)
        issues.append(
            "public bundle revoked: rights no longer allow public export; production.zip was quarantined to "
            + revoked.relative_to(root).as_posix() + "."
        )
    except OSError as exc:
        issues.append(f"public bundle must be revoked but could not be moved to quarantine: {exc}")


def _bundle_manifest_path(root: Path) -> Path:
    return root / "qa" / BUNDLE_MANIFEST_FILENAME


def record_bundle_manifest(project: str | Path, bundle_path: Path, *, bundle_kind: str) -> dict[str, Any]:
    """Bind the just-written production archive to the delivery record.

    The archive is written AFTER the stamp (so it can carry the stamp inside),
    which means the stamp itself cannot know the archive hash. This sidecar
    closes that hole: validate_delivery checks the expected bundle exists,
    opens, and matches size + SHA-256 (release audit v5.13.1 P0-2).
    """
    import os

    root = Path(project)
    if bundle_path.name not in BUNDLE_NAMES:
        raise ValueError(f"bundle name must be one of {sorted(BUNDLE_NAMES)}: {bundle_path.name}")
    record = {
        "schema_version": "1.0",
        "updated_at": _now(),
        "bundle": {
            "name": bundle_path.name,
            "tier": bundle_kind,
            "size": bundle_path.stat().st_size,
            "sha256": _sha256(bundle_path),
        },
    }
    qa_dir = root / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    target = _bundle_manifest_path(root)
    temp = target.with_name(target.name + ".tmp")
    temp.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, target)  # the sidecar IS the archive's commit point
    return record


def load_bundle_manifest(project: str | Path) -> dict[str, Any] | None:
    path = _bundle_manifest_path(Path(project))
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _check_bundles(root: Path, stamp: dict[str, Any] | None, issues: list[str]) -> None:
    """Expected bundle must exist unmodified; strays and orphans fail closed.

    The STAMP's promise is authoritative: when a successful compose recorded
    ``bundle_manifest_required``, a missing sidecar (or missing archive) is an
    unconditional failure — deciding based on whether a ZIP happens to still
    be visible on disk let "delete the ZIP and the sidecar together" validate
    clean (release audit v5.13.2 P0-1).
    """
    import zipfile

    final = root / "final"
    actual_bundles = sorted(path for path in final.glob("*") if path.is_file() and path.name in BUNDLE_NAMES) if final.is_dir() else []
    manifest = load_bundle_manifest(root)
    expected = manifest.get("bundle") if isinstance(manifest, dict) and isinstance(manifest.get("bundle"), dict) else None

    promised_name = str((stamp or {}).get("expected_bundle_name") or "")
    promised_tier = str((stamp or {}).get("expected_bundle_tier") or "")
    manifest_required = bool((stamp or {}).get("bundle_manifest_required")) or bool(promised_name)

    if expected is None:
        if manifest_required:
            issues.append(
                "delivery stamp promises a production bundle but qa/bundle-manifest.json is missing — "
                "the compose run did not complete its archive commit; re-run compose-project."
            )
        elif actual_bundles and stamp is not None:
            issues.append(
                "production bundle exists without qa/bundle-manifest.json — it was not written by the "
                "stamped compose run; re-run compose-project."
            )
        return

    name = str(expected.get("name") or "")
    tier = str(expected.get("tier") or "")
    if name not in BUNDLE_NAMES or "/" in name or "\\" in name:
        issues.append(f"bundle manifest names an illegal archive: {name!r} (must be one of {sorted(BUNDLE_NAMES)})")
        return
    if promised_name and name != promised_name:
        issues.append(
            f"bundle manifest names final/{name} but the stamped compose run promised final/{promised_name} — "
            "the sidecar was edited or belongs to another run."
        )
    if promised_tier and tier != promised_tier:
        issues.append(
            f"bundle manifest tier {tier!r} does not match the stamped rights tier {promised_tier!r}."
        )
    path = final / name
    if not path.is_file():
        issues.append(f"stamped production bundle is missing: final/{name}")
    else:
        if path.stat().st_size != expected.get("size") or _sha256(path) != expected.get("sha256"):
            issues.append(f"production bundle was replaced or modified after compose: final/{name}")
        else:
            try:
                with zipfile.ZipFile(path) as archive:
                    archive.namelist()
            except (zipfile.BadZipFile, OSError):
                issues.append(f"production bundle cannot be opened as a ZIP: final/{name}")
    for stray in actual_bundles:
        if stray.name != name:
            issues.append(f"unexpected production bundle not recorded by the stamped compose run: final/{stray.name}")


def validate_delivery(
    project: str | Path,
    *,
    raise_on_fail: bool = True,
    write_report: bool = True,
) -> dict[str, Any]:
    """Fail when final/ deliverables don't match the stamped, gated compose run."""
    root = Path(project)
    issues: list[str] = []
    stamp = load_delivery_stamp(root)
    current_inputs = input_fingerprints(root)
    actual_files = final_output_files(root)
    # "passed" means "the formal validation ran and held". Draft/quick/broken
    # directories are NOT validated — reporting passed=true for them let a
    # draft be presented (and series-status derive "composed") as if gates had
    # run (release audit v5.13.2 P0-3). applicable=False marks that case.
    applicable = True
    status = "validated"

    if not actual_files and stamp is None:
        # Nothing composed yet (init pre-creates empty final/cards + cover —
        # that is a neutral state, not deliverables written around the gates).
        passed = True
        status = "not-composed"
    elif not is_artifact_project(root):
        passed = True  # demo / quick runs are not gated projects
        applicable = False
        status = "not-applicable"
    elif stamp is None:
        issues.append(
            "final/ contains deliverable files without qa/delivery-gate.json: they were written "
            "around compose-project, so the gates never blessed them."
        )
        passed = False
    else:
        if stamp.get("forced"):
            reason = str(stamp.get("forced_reason") or "").strip()
            issues.append(f"delivery was forced past failing gates{': ' + reason if reason else ''}.")
        elif not stamp.get("passed"):
            issues.append("delivery stamp records a failing gate run.")

        # Inputs: story, approved panels, rights profile, project config.
        stamped_inputs = stamp.get("inputs") if isinstance(stamp.get("inputs"), dict) else {}
        if not stamped_inputs:
            issues.append("delivery stamp predates input/output binding — re-run compose-project to re-stamp.")
        else:
            labels = {
                "story_sha256": "story text",
                "approved_panels_sha256": "approved panel set",
                "grounding_profile_sha256": "grounding/rights profile",
                "project_sha256": "project configuration",
            }
            for key, label in labels.items():
                stamped_value = str(stamped_inputs.get(key) or "")
                if stamped_value != current_inputs[key]:
                    issues.append(f"{label} changed after the deliverable was composed: re-run compose-project.")

        # Outputs: every stamped file must exist unmodified; no strays.
        stamped_outputs = stamp.get("outputs") if isinstance(stamp.get("outputs"), dict) else None
        if stamped_outputs is None:
            issues.append("delivery stamp has no output manifest — re-run compose-project to re-stamp.")
        else:
            actual_by_rel = {path.relative_to(root).as_posix(): path for path in actual_files}
            for relative, meta in stamped_outputs.items():
                path = actual_by_rel.pop(relative, None)
                if path is None:
                    issues.append(f"stamped deliverable is missing: {relative}")
                    continue
                if not isinstance(meta, dict):
                    issues.append(f"stamped deliverable has no integrity record: {relative}")
                    continue
                if path.stat().st_size != meta.get("size") or _sha256(path) != meta.get("sha256"):
                    issues.append(f"deliverable was modified after compose: {relative}")
            for relative in sorted(actual_by_rel):
                issues.append(f"unexpected file in final/ not produced by the stamped compose run: {relative}")
            if not stamped_outputs:
                issues.append("delivery stamp lists no output files: the stamped run produced no deliverables.")

        # The production archive itself (written after the stamp) must match
        # the sidecar bundle manifest: exists, unmodified, openable, no strays.
        _check_bundles(root, stamp, issues)

        # Rights must hold NOW, not just at compose time.
        if stamp.get("public_export_allowed"):
            from .grounding_qa import evaluate_export_rights

            rights = evaluate_export_rights(root)
            if not rights["public_export_allowed"]:
                issues.append(
                    "rights status changed since compose: public export is no longer allowed ("
                    + "; ".join(rights["reasons"])
                    + ")."
                )
                _revoke_public_bundle(root, issues)
        passed = not issues

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": _now(),
        "passed": passed,
        "applicable": applicable,
        "status": status if passed else "failed",
        "has_final": bool(actual_files),
        "has_stamp": stamp is not None,
        "story_sha256": current_inputs["story_sha256"],
        "inputs": current_inputs,
        "issues": issues,
    }
    if write_report:
        qa_dir = root / "qa"
        qa_dir.mkdir(parents=True, exist_ok=True)
        (qa_dir / "delivery-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    if raise_on_fail and not passed:
        raise ValueError("Delivery gate failed: " + " ".join(issues))
    return report
