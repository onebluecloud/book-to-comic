"""Single source of truth for delivery-shape settings read from project.json.

Panel aspect ratio used to default to a hard-coded "3:2" (landscape) at every
prompt-build site, while the carousel cards are 1080x1440 (3:4 portrait). So the
default fought the delivery target: a landscape panel dropped into a portrait
card left the composer to crop it or pad it with caption bars. Worse, nothing
enforced consistency, so one episode could mix 3:2, 4:5 and 2:1 panels (the
桃花源记 failure) and still pass every gate.

This module centralises the delivery-shape config so prompt building, the
generation batch, and the aspect gate all read the same value.
"""

from __future__ import annotations

import json
from pathlib import Path

# Carousel cards and comic pages are portrait; default panels to match so the
# artwork fills the frame instead of being cropped or letterboxed.
DEFAULT_PANEL_ASPECT_RATIO = "3:4"

# Recognised ratios -> normalized width/height, for the consistency gate.
_KNOWN_RATIOS: dict[str, tuple[int, int]] = {
    "1:1": (1, 1),
    "3:4": (3, 4),
    "4:5": (4, 5),
    "2:3": (2, 3),
    "9:16": (9, 16),
    "4:3": (4, 3),
    "3:2": (3, 2),
    "16:9": (16, 9),
    "2:1": (2, 1),
}


def _read_project(root: Path) -> dict:
    try:
        data = json.loads((root / "project.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def project_panel_aspect_ratio(project: str | Path) -> str:
    """The episode-wide default panel aspect ratio.

    Reads ``panel_aspect_ratio`` from project.json, falling back to a portrait
    default that matches the carousel/comic-page delivery surfaces.
    """
    value = _read_project(Path(project)).get("panel_aspect_ratio")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return DEFAULT_PANEL_ASPECT_RATIO


def validate_panel_aspect_consistency(
    project: str | Path,
    *,
    tolerance: float = 0.06,
    write_report: bool = True,
    raise_on_fail: bool = True,
) -> dict:
    """Fail when panels in one episode disagree on aspect ratio.

    The composer slots one shape; panels that disagree get cropped (losing the
    top/bottom of tall art, as in the 琵琶行 landscape-slot crop) or letterboxed.
    A single episode mixing 3:4, 3:2 and 2:1 panels (the 桃花源记 failure) passed
    every other gate, so this gate exists specifically to catch that.

    Compares each approved panel PNG's measured ratio against the episode median;
    any panel more than ``tolerance`` (fractional) away from the median is flagged.
    """
    import json
    from pathlib import Path as _Path

    from PIL import Image

    root = _Path(project)
    manifest_path = root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        manifest = {"assets": []}

    approved = [
        item
        for item in manifest.get("assets", [])
        if item.get("kind") == "panel" and item.get("status") == "approved"
    ]
    measured: list[dict] = []
    for item in approved:
        canonical = root / str(item.get("canonical_path", ""))
        if not canonical.exists():
            continue
        with Image.open(canonical) as image:
            w, h = image.size
        measured.append({"panel_index": int(item.get("panel_index", 0)), "ratio": w / h if h else 0.0})

    issues: list[str] = []
    declared = project_panel_aspect_ratio(root)
    target = normalize_ratio_token(declared)
    target_ratio = (target[0] / target[1]) if target else None
    median = 0.0
    if measured:
        ratios = sorted(m["ratio"] for m in measured)
        median = ratios[len(ratios) // 2]
        for m in measured:
            if target_ratio is not None:
                # Primary check: the project's DECLARED target. A uniformly wrong
                # episode (three 16:9 panels in a 3:4 project) must fail — the old
                # median-only check waved exactly that through (2026-07 audit A7).
                if abs(m["ratio"] - target_ratio) / target_ratio > tolerance:
                    issues.append(
                        f"panel {m['panel_index']:02d} ratio {m['ratio']:.3f} deviates from declared target "
                        f"{declared} ({target_ratio:.3f})"
                    )
            elif median and abs(m["ratio"] - median) / median > tolerance:
                # Fallback when the declared value cannot be parsed: at least
                # require internal consistency across the episode.
                issues.append(
                    f"panel {m['panel_index']:02d} ratio {m['ratio']:.3f} deviates from episode median {median:.3f}"
                )

    passed = not issues
    report = {
        "schema_version": "1.1",
        "passed": passed,
        "panel_count": len(measured),
        "declared_target": declared,
        "target_ratio": round(target_ratio, 4) if target_ratio else None,
        "median_ratio": round(median, 4),
        "tolerance": tolerance,
        "issues": issues,
    }
    if write_report:
        qa_dir = root / "qa"
        qa_dir.mkdir(parents=True, exist_ok=True)
        (qa_dir / "aspect-consistency-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    if raise_on_fail and not passed:
        raise ValueError("Panel aspect ratios are inconsistent: " + "; ".join(issues))
    return report


def validate_panel_content_fill(
    project: str | Path,
    *,
    band_frac: float = 0.05,
    write_report: bool = True,
    raise_on_fail: bool = True,
) -> dict:
    """Fail when a panel's ARTWORK doesn't fill its canvas (letterbox/pillarbox).

    Image models sometimes answer a "3:4 vertical" request by painting a square
    or landscape picture ONTO a 3:4 sheet — flat margins, sometimes a drawn
    frame line. The file ratio then passes the aspect gate while the visible
    art is the wrong shape (2026-07 可能性的艺术 run: several panels shipped as
    framed pictures floating on paper). Detection: a top+bottom (or left+right)
    edge-band pair that is near-flat in color, matching each other, and clearly
    different from the image center is padding, not scenery.
    """
    import json
    from pathlib import Path as _Path

    from PIL import Image, ImageStat

    def _band_stats(image, box):
        stat = ImageStat.Stat(image.crop(box))
        return tuple(stat.mean), max(stat.stddev)

    def _color_delta(a, b):
        return max(abs(x - y) for x, y in zip(a, b))

    root = _Path(project)
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, ValueError):
        manifest = {"assets": []}
    approved = [
        item
        for item in manifest.get("assets", [])
        if item.get("kind") == "panel" and item.get("status") == "approved"
    ]

    issues: list[str] = []
    checked = 0
    for item in approved:
        canonical = root / str(item.get("canonical_path", ""))
        if not canonical.exists():
            continue
        with Image.open(canonical) as raw:
            image = raw.convert("RGB")
            w, h = image.size
            band_h = max(4, int(h * band_frac))
            band_w = max(4, int(w * band_frac))
            center_mean, _ = _band_stats(image, (int(w * 0.2), int(h * 0.2), int(w * 0.8), int(h * 0.8)))
            pairs = {
                "letterboxed (flat top/bottom margins)": (
                    _band_stats(image, (0, 0, w, band_h)),
                    _band_stats(image, (0, h - band_h, w, h)),
                ),
                "pillarboxed (flat left/right margins)": (
                    _band_stats(image, (0, 0, band_w, h)),
                    _band_stats(image, (w - band_w, 0, w, h)),
                ),
            }
        checked += 1
        for label, ((mean_a, std_a), (mean_b, std_b)) in pairs.items():
            flat = std_a < 10 and std_b < 10
            matching = _color_delta(mean_a, mean_b) < 16
            distinct = _color_delta(mean_a, center_mean) > 40 or _color_delta(mean_b, center_mean) > 40
            if flat and matching and distinct:
                issues.append(f"panel {int(item.get('panel_index', 0)):02d} looks {label}: artwork does not fill the canvas")

    passed = not issues
    report = {
        "schema_version": "1.0",
        "passed": passed,
        "panel_count": checked,
        "band_frac": band_frac,
        "issues": issues,
    }
    if write_report:
        qa_dir = root / "qa"
        qa_dir.mkdir(parents=True, exist_ok=True)
        (qa_dir / "content-fill-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    if raise_on_fail and not passed:
        raise ValueError(
            "Panel artwork does not fill the canvas (regenerate these panels full-bleed): " + "; ".join(issues)
        )
    return report


def normalize_ratio_token(value: str) -> tuple[int, int] | None:
    """Extract a width:height ratio from a free-form aspect string.

    Accepts values like "3:4", "4:5 vertical comic panel" or "portrait 2:3";
    returns the reduced (w, h) tuple, or None if no ratio can be parsed.
    """
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    # direct table hit on the leading token
    head = text.split()[0] if text.split() else ""
    if head in _KNOWN_RATIOS:
        return _KNOWN_RATIOS[head]
    # scan for an embedded "w:h"
    import re

    match = re.search(r"(\d+)\s*:\s*(\d+)", text)
    if match:
        w, h = int(match.group(1)), int(match.group(2))
        if w > 0 and h > 0:
            from math import gcd

            g = gcd(w, h)
            return (w // g, h // g)
    return None
