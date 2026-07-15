"""Grounding gate: was the adaptation-constraint homework done before drawing?

``planning/grounding_profile.json`` scores seven constraint dimensions
(see references/grounding/GROUNDING-MATRIX.md). This validator enforces the
scheduling contract:

* every dimension scoring >= 3 carries a rationale sentence;
* ``historical >= 3`` activates the visual-evidence contract — main characters
  in ``character_bible.json`` must carry ``social_class`` plus at least one of
  ``class_evidence`` / ``wardrobe_evidence`` (the 木兰 lesson: her wardrobe was
  invented as poor-peasant plain while the poem says 对镜贴花黄);
* gate dimensions (``rights`` / ``cultural``) at >= 4 emit a publish-time
  human-confirmation reminder instead of blocking — solo creators have no legal
  department, but they do read their own reports;
* the official compose path calls with ``require_profile=True``: no profile is
  a gate FAILURE there (2026-07 audit P0-1 — the public bundle used to ship
  without any rights homework). The standalone ``validate-grounding`` command
  keeps the legacy skip so old projects can still be inspected;
* ``evaluate_export_rights`` decides whether finished deliverables may enter
  the PUBLIC bundle: unlicensed in-copyright works, vague license claims and
  unconsented real-person/private material are private/debug-bundle only.

None of this verifies legal truth — it forces the declaration to be concrete
enough that a human can stand behind it, and fails closed when it is not.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DIMENSIONS = ("historical", "textual", "conceptual", "experiential", "procedural", "rights", "cultural")
GATE_DIMENSIONS = ("rights", "cultural")
ACTIVATE_AT = 3
REVIEW_AT = 4
COPYRIGHT_STATUSES = {"public_domain", "in_copyright", "licensed"}
# "licensed" is a self-reported declaration, not a verified grant. These fields
# force it to be concrete enough for a human to stand behind: who granted it,
# for which work/edition, and where the proof lives.
LICENSE_REQUIRED_FIELDS = ("rights_holder", "licensed_work", "proof_note")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def grounding_profile_path(root: Path) -> Path:
    return Path(root) / "planning" / "grounding_profile.json"


def load_grounding_profile(project: str | Path) -> dict[str, Any] | None:
    path = grounding_profile_path(Path(project))
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def validate_grounding(
    project: str | Path,
    *,
    raise_on_fail: bool = True,
    write_report: bool = True,
    require_profile: bool = False,
) -> dict[str, Any]:
    root = Path(project)
    profile = load_grounding_profile(root)
    issues: list[str] = []
    reminders: list[str] = []

    if profile is None:
        if require_profile:
            report = {
                "schema_version": "1.0",
                "updated_at": _now(),
                "passed": False,
                "skipped": False,
                "issues": [
                    "planning/grounding_profile.json is missing. The official compose path requires the "
                    "adaptation-constraint homework (seven 0-5 scores + copyright_status) before any deliverable "
                    "is emitted — write the profile per references/grounding/GROUNDING-MATRIX.md."
                ],
            }
            if write_report:
                _write(root, report)
            if raise_on_fail:
                raise ValueError("Grounding validation failed: " + " ".join(report["issues"]))
            return report
        report = {
            "schema_version": "1.0",
            "updated_at": _now(),
            "passed": True,
            "skipped": True,
            "note": "no planning/grounding_profile.json — legacy inspection only; the official compose path requires a profile.",
        }
        if write_report:
            _write(root, report)
        return report

    scores = profile.get("scores")
    if not isinstance(scores, dict):
        issues.append("profile.scores missing or not an object.")
        scores = {}
    parsed: dict[str, int] = {}
    for dim in DIMENSIONS:
        value = scores.get(dim)
        if not isinstance(value, int) or not 0 <= value <= 5:
            issues.append(f"scores.{dim} must be an integer 0-5.")
        else:
            parsed[dim] = value

    rationales = profile.get("rationales") if isinstance(profile.get("rationales"), dict) else {}
    for dim, value in parsed.items():
        if value >= ACTIVATE_AT and not str(rationales.get(dim) or "").strip():
            issues.append(f"{dim} scores {value} (>= {ACTIVATE_AT}) but has no rationale sentence.")

    # Deterministic content-safety record (release audit v5.13.2 P1-4): the
    # four hard exclusions (minor sexual content / self-harm methods /
    # real-person defamation / actionable illegal-harm guides) were promised
    # in SKILL.md prose but no gate ever required the host to record its
    # screening. This stays an honest HOST declaration — it is not a platform
    # legal review — but missing/unknown/hit now all block instead of shipping.
    safety = profile.get("content_safety")
    if not isinstance(safety, dict):
        issues.append(
            "content_safety record is missing: after screening the adaptation, write "
            '{"checked": true, "hard_exclusion_hits": []} (list any hit category instead of an empty list).'
        )
    else:
        if safety.get("checked") is not True:
            issues.append("content_safety.checked must be true — record the screening actually happened.")
        hits = safety.get("hard_exclusion_hits")
        if not isinstance(hits, list):
            issues.append("content_safety.hard_exclusion_hits must be a list ([] when clean).")
        elif hits:
            issues.append(
                "content_safety.hard_exclusion_hits is non-empty: hard-excluded content is refused outright — "
                "no private downgrade, no professional_review_note override. Hits: " + ", ".join(map(str, hits))
            )

    copyright_status = str(profile.get("copyright_status") or "").strip()
    if copyright_status not in COPYRIGHT_STATUSES:
        issues.append(f"copyright_status must be one of {sorted(COPYRIGHT_STATUSES)}.")
    elif copyright_status == "in_copyright":
        reminders.append(
            "copyright_status=in_copyright: personal-use only. compose-project will refuse the public "
            "bundle for this project; prefer a public-domain title for anything you intend to share."
        )
    elif copyright_status == "licensed":
        license_info = profile.get("license") if isinstance(profile.get("license"), dict) else {}
        missing = [field for field in LICENSE_REQUIRED_FIELDS if not str(license_info.get(field) or "").strip()]
        if missing:
            issues.append(
                "copyright_status=licensed requires a license object with concrete "
                f"{'/'.join(LICENSE_REQUIRED_FIELDS)}; missing: {', '.join(missing)}. "
                "A bare 'licensed' claim with no holder, work or proof reference is not a declaration anyone can stand behind."
            )
        else:
            reminders.append(
                f"licensed by {license_info['rights_holder']} for {license_info['licensed_work']}: "
                "keep the proof reachable and re-check scope/expiry before publishing."
            )
    elif copyright_status == "public_domain":
        if not str(profile.get("source_edition") or "").strip():
            issues.append(
                "copyright_status=public_domain requires source_edition naming the exact edition/translation used. "
                "The original being public domain does not clear a modern translation or annotated edition — "
                "declare which text you actually adapted."
            )

    if not isinstance(profile.get("real_person_or_private_source"), bool):
        issues.append(
            "real_person_or_private_source must be explicitly true or false — omitting it silently skipped "
            "the consent check (2026-07 release audit P0-4). Declare it."
        )
    elif profile.get("real_person_or_private_source") and not str(profile.get("consent_note") or "").strip():
        reminders.append(
            "real_person_or_private_source=true without consent_note: public export will be refused until a "
            "consent/release note is recorded (who agreed, to what, when)."
        )

    # High-consequence content (GROUNDING-MATRIX: medical, legal, dosage,
    # safety-critical procedure => procedural). A wrong dosage published as a
    # "formally passed" comic is not a style problem (release audit P0-5).
    if parsed.get("procedural", 0) >= REVIEW_AT and not str(profile.get("professional_review_note") or "").strip():
        reminders.append(
            f"procedural scores {parsed['procedural']} (>= {REVIEW_AT}): high-consequence content "
            "(medical/legal/dosage/dangerous procedure). Public export stays refused until "
            "professional_review_note records who with what qualification reviewed the facts and when."
        )

    for dim in GATE_DIMENSIONS:
        if parsed.get(dim, 0) >= REVIEW_AT:
            reminders.append(
                f"{dim} scores {parsed[dim]} (>= {REVIEW_AT}): human confirmation required before publishing "
                f"— {rationales.get(dim, 'see grounding matrix')}"
            )

    if parsed.get("historical", 0) >= ACTIVATE_AT:
        issues.extend(_check_character_evidence(root))

    passed = not issues
    report = {
        "schema_version": "1.0",
        "updated_at": _now(),
        "passed": passed,
        "skipped": False,
        "scores": parsed,
        "activated_dimensions": [d for d, v in parsed.items() if v >= ACTIVATE_AT],
        "publish_reminders": reminders,
        "issues": issues,
    }
    if write_report:
        _write(root, report)
    if raise_on_fail and not passed:
        raise ValueError("Grounding validation failed: " + " ".join(issues))
    return report


def _check_character_evidence(root: Path) -> list[str]:
    """historical >= 3: protagonists need social_class + sourced wardrobe."""
    bible_path = root / "planning" / "character_bible.json"
    if not bible_path.is_file():
        return ["historical >= 3 but planning/character_bible.json is missing."]
    try:
        bible = json.loads(bible_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"character_bible.json unreadable: {exc}"]
    characters = bible.get("characters") if isinstance(bible, dict) else None
    if not isinstance(characters, list):
        return ["character_bible.json has no characters list."]
    problems: list[str] = []
    for character in characters:
        if not isinstance(character, dict):
            continue
        role = str(character.get("role") or character.get("narrative_role") or "").lower()
        if "protagonist" not in role and "主角" not in role:
            continue
        name = str(character.get("name") or character.get("id") or "?")
        if not str(character.get("social_class") or "").strip():
            problems.append(
                f"historical constraint active: protagonist '{name}' has no social_class "
                "(the wardrobe/props follow from it — do the research, don't invent poverty or wealth)."
            )
        has_evidence = any(
            str(character.get(key) or "").strip()
            for key in ("class_evidence", "wardrobe_evidence")
        )
        if not has_evidence:
            problems.append(
                f"historical constraint active: protagonist '{name}' has neither class_evidence nor "
                "wardrobe_evidence (quote the source line, e.g. 木兰: 当窗理云鬓，对镜贴花黄)."
            )
    return problems


def evaluate_export_rights(project: str | Path) -> dict[str, Any]:
    """Decide whether finished deliverables may enter the PUBLIC bundle.

    This is deliberately separate from ``validate_grounding``: an unlicensed
    in-copyright adaptation is a legitimate personal-use project (gates can
    pass), it just must never leave the machine as a public production.zip.
    Returns ``public_export_allowed`` plus human-readable reasons; compose
    downgrades the bundle to private when it is False.
    """
    root = Path(project)
    profile = load_grounding_profile(root)
    reasons: list[str] = []
    status = ""
    hard_exclusion_hits: list[str] = []
    if profile is not None:
        safety = profile.get("content_safety")
        if isinstance(safety, dict) and isinstance(safety.get("hard_exclusion_hits"), list):
            hard_exclusion_hits = [str(hit) for hit in safety["hard_exclusion_hits"] if str(hit).strip()]
    if profile is None:
        reasons.append("no grounding profile: rights status unknown, public export refused.")
    else:
        status = str(profile.get("copyright_status") or "").strip()
        if status == "in_copyright":
            reasons.append(
                "copyright_status=in_copyright with no recorded license: private/debug bundle only."
            )
        elif status == "licensed":
            license_info = profile.get("license") if isinstance(profile.get("license"), dict) else {}
            missing = [field for field in LICENSE_REQUIRED_FIELDS if not str(license_info.get(field) or "").strip()]
            if missing:
                reasons.append(f"licensed claim is incomplete (missing {', '.join(missing)}): public export refused.")
        elif status == "public_domain":
            if not str(profile.get("source_edition") or "").strip():
                reasons.append("public_domain without source_edition: declare the exact edition/translation first.")
        else:
            reasons.append(f"copyright_status {status!r} is not a recognized rights declaration.")
        real_person = profile.get("real_person_or_private_source")
        if not isinstance(real_person, bool):
            reasons.append(
                "real_person_or_private_source is not explicitly declared (true/false): public export refused."
            )
        elif real_person and not str(profile.get("consent_note") or "").strip():
            reasons.append("real-person/private source material without a consent_note: public export refused.")
        scores = profile.get("scores") if isinstance(profile.get("scores"), dict) else {}
        procedural = scores.get("procedural")
        if isinstance(procedural, int) and procedural >= REVIEW_AT and not str(profile.get("professional_review_note") or "").strip():
            reasons.append(
                "high-consequence content (procedural >= "
                f"{REVIEW_AT}: medical/legal/dosage/dangerous procedure) without a professional_review_note: "
                "private bundle only until a qualified review is recorded."
            )
    return {
        "copyright_status": status or "unknown",
        "public_export_allowed": not reasons and not hard_exclusion_hits,
        "reasons": reasons,
        "hard_exclusion_hits": hard_exclusion_hits,
    }


def _write(root: Path, report: dict[str, Any]) -> None:
    qa_dir = root / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    (qa_dir / "grounding-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
