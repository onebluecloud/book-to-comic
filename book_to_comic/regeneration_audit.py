from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


class RegenerationAuditError(ValueError):
    pass


FINAL_FILES = (
    "comic-long.png",
    "comic.pdf",
    "comic.cbz",
    "comic.epub",
    # All bundle tiers: compose emits exactly one of these per run.
    "production.zip",
    "production-private.zip",
    "production-debug.zip",
)


def audit_regeneration(
    project: str | Path,
    *,
    against: str | Path,
    require_new_panels: bool = False,
    write_report: bool = True,
) -> dict[str, Any]:
    root = Path(project)
    baseline = Path(against)
    current_panels = _panel_hashes(root)
    baseline_panels = _panel_hashes(baseline)
    if not current_panels:
        raise RegenerationAuditError(f"No current panel assets found: {root}")
    if not baseline_panels:
        raise RegenerationAuditError(f"No baseline panel assets found: {baseline}")

    compared_panel_ids = sorted(set(current_panels) & set(baseline_panels), key=_panel_sort_key)
    reused_panel_ids = [panel_id for panel_id in compared_panel_ids if current_panels[panel_id] == baseline_panels[panel_id]]
    changed_panel_ids = [panel_id for panel_id in compared_panel_ids if current_panels[panel_id] != baseline_panels[panel_id]]
    new_panel_ids = sorted(set(current_panels) - set(baseline_panels), key=_panel_sort_key)
    missing_baseline_panel_ids = sorted(set(baseline_panels) - set(current_panels), key=_panel_sort_key)

    current_cards = _file_hashes(root / "final" / "cards", "*.png")
    baseline_cards = _file_hashes(baseline / "final" / "cards", "*.png")
    compared_cards = sorted(set(current_cards) & set(baseline_cards))
    reused_cards = [name for name in compared_cards if current_cards[name] == baseline_cards[name]]
    changed_cards = [name for name in compared_cards if current_cards[name] != baseline_cards[name]]

    final_files = []
    for name in FINAL_FILES:
        current_path = root / "final" / name
        baseline_path = baseline / "final" / name
        if current_path.exists() and baseline_path.exists():
            current_hash = _sha256(current_path)
            baseline_hash = _sha256(baseline_path)
            final_files.append(
                {
                    "file": name,
                    "same": current_hash == baseline_hash,
                    "current_sha256": current_hash,
                    "baseline_sha256": baseline_hash,
                }
            )

    if compared_panel_ids and len(reused_panel_ids) == len(compared_panel_ids):
        status = "repack_only" if compared_cards and len(reused_cards) == len(compared_cards) else "lettering_or_packaging_only"
    elif reused_panel_ids:
        status = "partial_visual_regeneration"
    elif compared_panel_ids:
        status = "visual_regeneration"
    else:
        status = "no_comparable_panels"

    passed = not require_new_panels or (bool(compared_panel_ids) and not reused_panel_ids)
    report = {
        "schema_version": "1.0",
        "updated_at": _now(),
        "project": str(root),
        "against": str(baseline),
        "require_new_panels": require_new_panels,
        "passed": passed,
        "status": status,
        "metrics": {
            "current_panel_count": len(current_panels),
            "baseline_panel_count": len(baseline_panels),
            "compared_panel_count": len(compared_panel_ids),
            "reused_panel_count": len(reused_panel_ids),
            "changed_panel_count": len(changed_panel_ids),
            "new_panel_count": len(new_panel_ids),
            "missing_baseline_panel_count": len(missing_baseline_panel_ids),
            "compared_card_count": len(compared_cards),
            "reused_card_count": len(reused_cards),
            "changed_card_count": len(changed_cards),
        },
        "reused_panel_ids": reused_panel_ids,
        "changed_panel_ids": changed_panel_ids,
        "new_panel_ids": new_panel_ids,
        "missing_baseline_panel_ids": missing_baseline_panel_ids,
        "reused_cards": reused_cards,
        "changed_cards": changed_cards,
        "final_files": final_files,
        "truth_statement": _truth_statement(status, len(changed_panel_ids), len(compared_panel_ids), len(changed_cards), len(compared_cards)),
    }
    if write_report:
        _write_json(root / "qa" / "regeneration-audit-report.json", report)
    if require_new_panels and not passed:
        raise RegenerationAuditError(report["truth_statement"])
    return report


def _panel_hashes(root: Path) -> dict[str, str]:
    manifest_path = root / "manifest.json"
    panels: dict[str, str] = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}
        assets = manifest.get("assets") if isinstance(manifest, Mapping) else []
        if isinstance(assets, list):
            for item in assets:
                if not isinstance(item, Mapping):
                    continue
                if item.get("kind") != "panel" or item.get("status") != "approved":
                    continue
                panel_id = _panel_id(item)
                digest = _text(item.get("canonical_sha256") or item.get("sha256"))
                canonical_path = _text(item.get("canonical_path"))
                if canonical_path and (not digest or len(digest) != 64):
                    path = root / canonical_path
                    digest = _sha256(path) if path.exists() else digest
                if panel_id and digest:
                    panels[panel_id] = digest
    if panels:
        return panels
    panel_dir = root / "assets" / "panels"
    return {path.stem: _sha256(path) for path in sorted(panel_dir.glob("*.png"))}


def _panel_id(item: Mapping[str, Any]) -> str:
    panel_index = item.get("panel_index")
    if isinstance(panel_index, int):
        return f"{panel_index:02d}"
    if isinstance(panel_index, str) and panel_index.strip().isdigit():
        return f"{int(panel_index):02d}"
    asset_id = _text(item.get("asset_id"))
    if asset_id.startswith("panel-"):
        suffix = asset_id.removeprefix("panel-")
        return f"{int(suffix):02d}" if suffix.isdigit() else suffix
    return asset_id


def _file_hashes(directory: Path, pattern: str) -> dict[str, str]:
    if not directory.exists():
        return {}
    return {path.name: _sha256(path) for path in sorted(directory.glob(pattern)) if path.is_file()}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _truth_statement(status: str, changed_panels: int, compared_panels: int, changed_cards: int, compared_cards: int) -> str:
    if status == "repack_only":
        return f"0/{compared_panels} panel images changed and 0/{compared_cards} cards changed; this is a repack, not a new visual generation."
    if status == "lettering_or_packaging_only":
        return f"0/{compared_panels} panel images changed; {changed_cards}/{compared_cards} cards changed through lettering or packaging only."
    if status == "partial_visual_regeneration":
        return f"{changed_panels}/{compared_panels} panel images changed; this is a partial visual regeneration."
    if status == "visual_regeneration":
        return f"{changed_panels}/{compared_panels} comparable panel images changed; this can be described as a new visual generation."
    return "No comparable panel images were found between current and baseline projects."


def _panel_sort_key(panel_id: str) -> tuple[int, str]:
    return (int(panel_id), panel_id) if panel_id.isdigit() else (10**9, panel_id)


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
