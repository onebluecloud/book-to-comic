from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

from .codex_cli_bootstrap import ensure_codex_cli
from .codex_image_worker import run_codex_exec_image_selftest


DEFAULT_CODEX_BIN = "codex"


@dataclass
class BackendStatus:
    id: str
    label: str
    status: str
    usable_for_final: bool
    round_trip: bool
    reason: str
    command: str = ""
    details: dict[str, object] = field(default_factory=dict)


def probe_image_backends(
    *,
    project_dir: str | Path | None = None,
    codex_bin: str | None = None,
    timeout_seconds: int = 8,
    run_image_selftest: bool = False,
    image_selftest_timeout_seconds: int = 300,
) -> dict[str, object]:
    """Probe save-capable image backends for zero-touch final comic generation.

    Final comic generation has a stricter bar than previewing an image in chat:
    a backend is usable only when it can write local PNG files that the project
    can import, validate, compose, and export without user file handling.
    """
    backend_items = [
        _probe_codex_exec_image_worker(
            codex_bin=codex_bin,
            timeout_seconds=timeout_seconds,
            run_image_selftest=run_image_selftest,
            image_selftest_timeout_seconds=image_selftest_timeout_seconds,
        ),
        _host_native_save_tool_status(),
        _local_model_status(),
        _external_api_status(),
        _manual_import_status(),
    ]
    selected = next((item.id for item in backend_items if item.usable_for_final), None)
    return {
        "schema_version": "1.0",
        "python_executable": Path(sys.executable).name,
        "project_dir": str(project_dir) if project_dir else "",
        "saved_png_contract": {
            "required": True,
            "image_selftest_required_for_final": True,
            "acceptance": [
                "backend writes one PNG per panel to a local directory",
                "files are named 01.png through NN.png",
                "import-host-images can read them and pass size/non-empty checks",
                "compose/export run from imported panel files, not chat previews",
            ],
            "preview_only_is_valid": False,
        },
        "final_backend_ready": selected is not None,
        "selected_backend": selected,
        "backends": [asdict(item) for item in backend_items],
    }


def write_image_backend_report(project_dir: str | Path, report: dict[str, object]) -> Path:
    root = Path(project_dir)
    report_path = root / "image-backend-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    report_path.write_text(text, encoding="utf-8")
    qa_path = root / "qa" / "image-backend-report.json"
    qa_path.parent.mkdir(parents=True, exist_ok=True)
    qa_path.write_text(text, encoding="utf-8")
    return report_path


def format_backend_blocker(report: dict[str, object]) -> str:
    reasons = []
    for item in report.get("backends", []):
        if not isinstance(item, dict):
            continue
        if item.get("usable_for_final"):
            continue
        reasons.append(f"{item.get('id')}: {item.get('reason')}")
    joined = "; ".join(reasons) if reasons else "no usable backend reported"
    return (
        "No save-capable image backend is ready. Final high-quality comics require "
        f"local PNG round-trip; chat preview images are not enough. Details: {joined}"
    )


def _probe_codex_exec_image_worker(
    codex_bin: str | None,
    timeout_seconds: int,
    *,
    run_image_selftest: bool,
    image_selftest_timeout_seconds: int,
) -> BackendStatus:
    if not codex_bin:
        bootstrap = ensure_codex_cli(install=False, timeout_seconds=timeout_seconds)
        selected = bootstrap.get("selected_bin")
        if selected:
            return _codex_image_worker_status_from_launchable(
                str(selected),
                details={"bootstrap": bootstrap},
                run_image_selftest=run_image_selftest,
                image_selftest_timeout_seconds=image_selftest_timeout_seconds,
            )

        candidates = bootstrap.get("candidates", [])
        if candidates:
            blocked = "; ".join(
                f"{item.get('source')}: {item.get('status')} {item.get('reason')}"
                for item in candidates
                if isinstance(item, dict)
            )
            return BackendStatus(
                id="codex-exec-image-worker",
                label="Codex exec image worker",
                status="blocked",
                usable_for_final=False,
                round_trip=True,
                command="codex",
                reason=f"No launchable ordinary Codex CLI was found. {blocked}",
                details={"bootstrap": bootstrap},
            )

    requested = codex_bin or os.environ.get("BOOK_TO_COMIC_CODEX_BIN") or DEFAULT_CODEX_BIN
    resolved = _resolve_command(requested)
    if not resolved:
        return BackendStatus(
            id="codex-exec-image-worker",
            label="Codex exec image worker",
            status="not-found",
            usable_for_final=False,
            round_trip=True,
            command=requested,
            reason=f"`{requested}` was not found on PATH, so the dedicated image worker cannot start.",
        )

    try:
        completed = subprocess.run(
            [resolved, "--version"],
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except PermissionError as exc:
        return BackendStatus(
            id="codex-exec-image-worker",
            label="Codex exec image worker",
            status="blocked",
            usable_for_final=False,
            round_trip=True,
            command=resolved,
            reason=f"`{resolved}` exists but cannot be launched: {exc}",
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return BackendStatus(
            id="codex-exec-image-worker",
            label="Codex exec image worker",
            status="blocked",
            usable_for_final=False,
            round_trip=True,
            command=resolved,
            reason=f"`{resolved}` could not complete the launch self-test: {exc}",
        )

    if completed.returncode != 0:
        stderr = completed.stderr.strip() or completed.stdout.strip()
        return BackendStatus(
            id="codex-exec-image-worker",
            label="Codex exec image worker",
            status="blocked",
            usable_for_final=False,
            round_trip=True,
            command=resolved,
            reason=f"`{resolved}` launch self-test failed with exit code {completed.returncode}: {stderr}",
        )

    return _codex_image_worker_status_from_launchable(
        resolved,
        details={"version": (completed.stdout.strip() or completed.stderr.strip())},
        run_image_selftest=run_image_selftest,
        image_selftest_timeout_seconds=image_selftest_timeout_seconds,
    )


def _codex_image_worker_status_from_launchable(
    command: str,
    *,
    details: dict[str, object],
    run_image_selftest: bool,
    image_selftest_timeout_seconds: int,
) -> BackendStatus:
    if not run_image_selftest:
        merged_details = dict(details)
        merged_details["image_selftest"] = {
            "attempted": False,
            "ok": False,
            "reason": "image self-test was not requested",
        }
        return BackendStatus(
            id="codex-exec-image-worker",
            label="Codex exec image worker",
            status="launchable-needs-image-selftest",
            usable_for_final=False,
            round_trip=False,
            command=command,
            reason=(
                "Codex CLI launches, but final comics require a live image self-test that writes "
                "a local PNG. Run doctor-image-backends --selftest-image or generate-final."
            ),
            details=merged_details,
        )

    selftest = run_codex_exec_image_selftest(
        codex_bin=command,
        timeout_seconds=image_selftest_timeout_seconds,
    )
    merged_details = dict(details)
    merged_details["image_selftest"] = selftest
    if selftest.get("ok"):
        return BackendStatus(
            id="codex-exec-image-worker",
            label="Codex exec image worker",
            status="available",
            usable_for_final=True,
            round_trip=True,
            command=command,
            reason="Codex CLI launches and the image worker saved an importable local PNG.",
            details=merged_details,
        )

    return BackendStatus(
        id="codex-exec-image-worker",
        label="Codex exec image worker",
        status="image-selftest-failed",
        usable_for_final=False,
        round_trip=False,
        command=command,
        reason=f"Codex CLI launches, but image self-test failed: {selftest.get('reason')}",
        details=merged_details,
    )


def _host_native_save_tool_status() -> BackendStatus:
    return BackendStatus(
        id="host-native-save-tool",
        label="Host native save-capable image tool",
        status="host-mediated",
        usable_for_final=False,
        round_trip=True,
        reason=(
            "Python cannot introspect chat-only image tools. The Skill may use this path only when "
            "the current Codex/Claude host exposes image bytes or a local file path; preview-only output is rejected."
        ),
    )


def _local_model_status() -> BackendStatus:
    detected = _detect_local_model_marker()
    if detected:
        return BackendStatus(
            id="local-model",
            label="Local image model",
            status="detected-adapter-required",
            usable_for_final=False,
            round_trip=True,
            command=detected,
            reason=(
                f"Detected `{detected}`, but this build has not enabled a local-model save adapter. "
                "It cannot be selected for zero-touch final generation yet."
            ),
        )
    return BackendStatus(
        id="local-model",
        label="Local image model",
        status="not-detected",
        usable_for_final=False,
        round_trip=True,
        reason="No ComfyUI/Automatic1111/Diffusers marker was detected for an automatic local PNG workflow.",
    )


def _external_api_status() -> BackendStatus:
    enabled = os.environ.get("BOOK_TO_COMIC_ENABLE_EXTERNAL_API") == "1"
    has_key = any(os.environ.get(name) for name in ("OPENAI_API_KEY", "REPLICATE_API_TOKEN", "FAL_KEY"))
    return BackendStatus(
        id="external-api",
        label="External image API",
        status="enabled" if enabled and has_key else "disabled",
        usable_for_final=False,
        round_trip=True,
        reason=(
            "External API mode is an explicit optional extension, not a default no-config backend."
            if not enabled
            else "External API variables are present, but this build keeps API adapters outside the default path."
        ),
    )


def _manual_import_status() -> BackendStatus:
    return BackendStatus(
        id="manual-import",
        label="Manual saved image import",
        status="available-but-not-zero-touch",
        usable_for_final=False,
        round_trip=True,
        reason=(
            "`import-host-images` can import a folder of finished PNGs, but it is not a zero-touch generation backend."
        ),
    )


def _resolve_command(command: str) -> str | None:
    command_path = Path(command)
    if command_path.exists():
        return str(command_path)
    return shutil.which(command)


def redact_url(value: str) -> str:
    """scheme://host[:port] only — no userinfo, path, query or fragment.

    Diagnostics used to echo the raw env value, leaking basic-auth passwords
    and query tokens into reports and terminal logs (audit P1-6).
    """
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(value)
    except ValueError:
        return "<unparseable-url>"
    if not parts.scheme or not parts.netloc:
        return "<non-url-value>"
    host = parts.hostname or ""
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{host}{port}"


def _detect_local_model_marker() -> str:
    for env_name in ("BOOK_TO_COMIC_COMFYUI_URL", "COMFYUI_URL", "A1111_URL"):
        value = os.environ.get(env_name)
        if value:
            return f"{env_name}={redact_url(value)}"
    for command in ("comfy", "comfyui", "automatic1111", "a1111"):
        resolved = shutil.which(command)
        if resolved:
            return resolved
    return ""
