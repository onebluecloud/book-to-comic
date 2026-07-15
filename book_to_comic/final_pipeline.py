from __future__ import annotations

from pathlib import Path
from typing import Any

from .codex_cli_bootstrap import ensure_codex_cli
from .codex_image_worker import run_codex_exec_image_batches
from .host_image_batch import prepare_host_image_batch
from .image_assets import import_host_image_panels
from .image_backends import format_backend_blocker, probe_image_backends, write_image_backend_report
from .project_layout import load_episode
from .project_workflow import compose_project, export_project


DEFAULT_FORMATS = "pdf,cbz,epub,long-image,zip"


def generate_final_comic(
    project_dir: str | Path,
    *,
    backend: str = "auto",
    formats: str = DEFAULT_FORMATS,
    codex_bin: str | None = None,
    # Portrait 3:4 to match DEFAULT_PANEL_ASPECT_RATIO (audit E2: the old 1536x1024
    # landscape default fought the 3:4 delivery target and forced the aspect gate to
    # reject every panel). Callers can still override for landscape projects.
    width: int = 1152,
    height: int = 1536,
    quality: str = "high",
    bootstrap_codex: bool = True,
    image_selftest_timeout_seconds: int = 300,
) -> dict[str, object]:
    """Run the zero-touch final-comic gate for a host-image project.

    The function prepares deterministic image jobs for every episode, probes
    save-capable backends, and refuses to continue unless a backend can produce
    importable local PNG files. It deliberately does not fall back to vector
    when the caller asks for final high-quality comics.
    """
    root = Path(project_dir)
    if not root.exists():
        raise FileNotFoundError(f"Project directory does not exist: {root}")

    episode_ids = discover_episode_ids(root)
    if not episode_ids:
        raise FileNotFoundError(f"No official episode found at {root / 'story' / 'episode-001.json'}")

    prepared_batches = [
        prepare_host_image_batch(
            root,
            episode_id=episode_id,
            width=width,
            height=height,
            quality=quality,
        )
        for episode_id in episode_ids
    ]

    bootstrap_report = None
    effective_codex_bin = codex_bin
    if bootstrap_codex and not codex_bin:
        bootstrap_report = ensure_codex_cli(install=True)
        selected_bin = bootstrap_report.get("selected_bin")
        if selected_bin:
            effective_codex_bin = str(selected_bin)

    report = probe_image_backends(
        project_dir=root,
        codex_bin=effective_codex_bin,
        run_image_selftest=True,
        image_selftest_timeout_seconds=image_selftest_timeout_seconds,
    )
    report["requested_backend"] = backend
    report["requested_formats"] = formats
    if bootstrap_report is not None:
        report["codex_cli_bootstrap"] = bootstrap_report
    report["prepared_batches"] = _jsonable_batches(prepared_batches)
    report_path = write_image_backend_report(root, report)

    selected = _select_backend(report, requested=backend)
    if not selected:
        raise ValueError(f"{format_backend_blocker(report)} Report: {report_path}")

    if selected != "codex-exec-image-worker":
        raise ValueError(f"Backend `{selected}` is not wired into this build's zero-touch runner. Report: {report_path}")

    worker_results = run_codex_exec_image_batches(prepared_batches, codex_bin=effective_codex_bin)
    import_results = [
        import_host_image_panels(root, batch["image_dir"], episode_id=str(batch["episode_id"]))
        for batch in prepared_batches
    ]
    composed = compose_project(root)
    exported = export_project(root, formats=formats)
    return {
        "project_dir": str(root),
        "backend": selected,
        "report": str(report_path),
        "prepared_batches": _jsonable_batches(prepared_batches),
        "worker_results": worker_results,
        "import_results": import_results,
        "composed": {key: str(value) for key, value in composed.items()},
        "exported": {key: str(value) for key, value in exported.items()},
    }


def discover_episode_ids(project_dir: str | Path) -> list[str]:
    root = Path(project_dir)
    try:
        episode = load_episode(root)
    except (FileNotFoundError, OSError, ValueError):
        return []
    episode_id = str(episode.get("episode_id") or "EP01").strip()
    return [episode_id or "EP01"]


def _select_backend(report: dict[str, object], *, requested: str) -> str | None:
    if requested == "auto":
        selected = report.get("selected_backend")
        return str(selected) if selected else None
    for item in report.get("backends", []):
        if not isinstance(item, dict):
            continue
        if item.get("id") == requested and item.get("usable_for_final"):
            return requested
    return None


def _jsonable_batches(batches: list[dict[str, Any]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for batch in batches:
        result.append(
            {
                "episode_id": batch["episode_id"],
                "panel_count": batch["panel_count"],
                "jobs_file": batch["jobs_file"],
                "image_dir": batch["image_dir"],
                "manifest": batch["manifest"],
            }
        )
    return result
