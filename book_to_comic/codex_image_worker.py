from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any

from .codex_cli_bootstrap import DEFAULT_TOOLS_DIR, default_managed_codex_bin


SUPPORTED_OUTPUT_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
DEFAULT_SELFTEST_DIR = DEFAULT_TOOLS_DIR / "image-worker-selftest"


def run_codex_exec_image_selftest(
    *,
    codex_bin: str | None = None,
    test_dir: str | Path | None = None,
    timeout_seconds: int = 300,
    min_file_bytes: int = 50_000,
) -> dict[str, object]:
    """Verify that the Codex worker can create a real local image file.

    This is intentionally a live, end-to-end smoke test. A launchable Codex CLI
    is not enough for final comics; the worker must save or recover a local PNG
    that the deterministic import pipeline can consume.
    """
    root = Path(test_dir or os.environ.get("BOOK_TO_COMIC_IMAGE_SELFTEST_DIR", DEFAULT_SELFTEST_DIR))
    run_root = root / f"selftest-{int(time.time() * 1000)}"
    image_dir = run_root / "images"
    jobs_file = run_root / "jobs.jsonl"
    run_root.mkdir(parents=True, exist_ok=True)
    job = {
        "id": "selftest-P01",
        "output": "01.png",
        "size": "512x512",
        "prompt": (
            "High-quality editorial comic panel, a small brass key on a wooden desk, "
            "warm paper texture, elegant ink-and-wash illustration, no readable text, no watermark."
        ),
    }
    jobs_file.write_text(json.dumps(job, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        result = run_codex_exec_image_batch(
            jobs_file,
            image_dir,
            codex_bin=codex_bin,
            timeout_seconds=timeout_seconds,
        )
        output = image_dir / "01.png"
        if not output.exists():
            return {
                "attempted": True,
                "ok": False,
                "reason": f"self-test worker returned without writing {output}",
                "run_dir": str(run_root),
                "worker_result": result,
            }
        file_bytes = output.stat().st_size
        if file_bytes < min_file_bytes:
            return {
                "attempted": True,
                "ok": False,
                "reason": f"self-test PNG is too small for high-quality final art: {file_bytes} bytes",
                "run_dir": str(run_root),
                "output_file": str(output),
                "file_bytes": file_bytes,
                "worker_result": result,
            }
        return {
            "attempted": True,
            "ok": True,
            "reason": "codex-exec-image-worker saved an importable local PNG",
            "run_dir": str(run_root),
            "output_file": str(output),
            "file_bytes": file_bytes,
            "worker_result": result,
        }
    except Exception as exc:
        return {
            "attempted": True,
            "ok": False,
            "reason": _short_reason(str(exc)),
            "run_dir": str(run_root),
        }


def run_codex_exec_image_batches(
    prepared_batches: list[dict[str, Any]],
    *,
    codex_bin: str | None = None,
    timeout_seconds: int = 900,
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for batch in prepared_batches:
        results.append(
            run_codex_exec_image_batch(
                batch["jobs_file"],
                batch["image_dir"],
                codex_bin=codex_bin,
                timeout_seconds=timeout_seconds,
            )
        )
    return results


def run_codex_exec_image_batch(
    jobs_file: str | Path,
    image_dir: str | Path,
    *,
    codex_bin: str | None = None,
    timeout_seconds: int = 900,
) -> dict[str, object]:
    """Run the dedicated Codex image worker and recover local image files.

    This adapter is intentionally narrow: it reads precompiled panel-image jobs,
    asks a child Codex session to generate one image per job, and copies the
    saved file into the required output directory. It must not research books,
    rewrite panels, add text, or make story decisions.
    """
    resolved_codex = _resolve_command(codex_bin or os.environ.get("BOOK_TO_COMIC_CODEX_BIN") or str(default_managed_codex_bin()))
    if not resolved_codex:
        raise FileNotFoundError("Codex CLI was not found; cannot run codex-exec-image-worker")

    jobs_path = Path(jobs_file)
    output_root = Path(image_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    jobs = [json.loads(line) for line in jobs_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    written: list[str] = []
    base_dir = output_root.resolve()
    for job in jobs:
        output = output_root / str(job["output"])
        # Job files can come from anywhere; never let an output entry walk out
        # of the image dir (same traversal class as the asset_id audit finding).
        if not output.resolve().is_relative_to(base_dir):
            raise ValueError(f"job output escapes the image dir: {job.get('output')!r}")
        if output.exists() and output.stat().st_size > 0:
            written.append(str(output))
            continue

        before = _snapshot_generated_images()
        prompt = _worker_prompt(job, output)
        completed = _run_worker_command(
            [
                resolved_codex,
                "exec",
                "--sandbox",
                # Least privilege (2026-07 audit A4): the worker only needs to
                # save an image under its own output dir. Never full access and
                # never --ignore-rules by default; users who truly need broader
                # access opt in explicitly via BOOK_TO_COMIC_WORKER_SANDBOX.
                os.environ.get("BOOK_TO_COMIC_WORKER_SANDBOX", "workspace-write"),
                "--skip-git-repo-check",
                "--enable",
                "image_generation",
                "-",
            ],
            prompt,
            timeout_seconds=timeout_seconds,
        )
        _write_worker_log(output_root, job, completed.stdout, completed.stderr)
        if completed.returncode != 0:
            failure_text = completed.stderr.strip() or completed.stdout.strip()
            raise ValueError(
                "codex-exec-image-worker failed for "
                f"{job.get('id', job.get('output'))}: {_short_reason(failure_text)}"
            )
        if "IMAGE_TOOL_UNAVAILABLE" in completed.stdout or "IMAGE_TOOL_UNAVAILABLE" in completed.stderr:
            raise ValueError(
                "codex-exec-image-worker reported IMAGE_TOOL_UNAVAILABLE for "
                f"{job.get('id', job.get('output'))}"
            )
        if _looks_like_procedural_fallback(completed.stdout + "\n" + completed.stderr):
            raise ValueError(
                "codex-exec-image-worker appears to have used procedural/vector drawing instead of "
                f"host-native AI image generation for {job.get('id', job.get('output'))}"
            )

        recovered = _path_from_output(completed.stdout) or _newest_generated_image(before)
        if not recovered:
            raise ValueError(
                "codex-exec-image-worker did not return or create a recoverable local image file "
                f"for {job.get('id', job.get('output'))}. Preview-only image output is not acceptable."
            )
        _copy_as_png_source(recovered, output)
        written.append(str(output))

    return {
        "backend": "codex-exec-image-worker",
        "jobs_file": str(jobs_path),
        "image_dir": str(output_root),
        "written": written,
        "image_count": len(written),
    }


def _worker_prompt(job: dict[str, Any], output: Path) -> str:
    return (
        "Generate one AI raster image now using the built-in image generation tool.\n"
        "Create exactly one high-quality raster comic panel from the prompt below.\n"
        "Do not research, rewrite, translate, storyboard, add captions, add speech bubbles, or render readable text.\n"
        f"Save the final image as a local PNG at this exact path if your host image tool supports saving: {output}\n"
        "If the image tool saves to its own generated_images folder, return the saved local file path only.\n"
        "Do not use Python, PIL, SVG, HTML, canvas, screenshots, procedural drawing, placeholder art, or vector rendering as a substitute for AI image generation.\n"
        "If the built-in image generation tool is unavailable, fail explicitly with IMAGE_TOOL_UNAVAILABLE and do not create any image file.\n"
        "A chat preview without a local file is a failure.\n\n"
        f"Panel id: {job.get('id', '')}\n"
        f"Required size: {job.get('size', '')}\n"
        f"Prompt:\n{job.get('prompt', '')}\n"
    )


def _run_worker_command(command: list[str], prompt: str, *, timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creationflags,
    )
    try:
        stdout, stderr = process.communicate(prompt, timeout=timeout_seconds)
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    except subprocess.TimeoutExpired as exc:
        _terminate_process_tree(process)
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        timeout_message = f"Timed out after {timeout_seconds} seconds"
        stderr = (stderr or "").rstrip()
        stderr = f"{stderr}\n{timeout_message}" if stderr else timeout_message
        return subprocess.CompletedProcess(command, 124, stdout or "", stderr)


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
        return
    process.kill()


def _write_worker_log(output_root: Path, job: dict[str, Any], stdout: str, stderr: str) -> None:
    logs = output_root / "_worker-logs"
    logs.mkdir(parents=True, exist_ok=True)
    job_id = str(job.get("id") or job.get("output") or "panel").replace("/", "_").replace("\\", "_")
    (logs / f"{job_id}.stdout.txt").write_text(stdout or "", encoding="utf-8", errors="replace")
    (logs / f"{job_id}.stderr.txt").write_text(stderr or "", encoding="utf-8", errors="replace")


def _snapshot_generated_images() -> dict[Path, int]:
    snapshot: dict[Path, int] = {}
    for directory in _candidate_generated_dirs():
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if path.is_file() and path.suffix.lower() in SUPPORTED_OUTPUT_SUFFIXES:
                try:
                    snapshot[path.resolve()] = path.stat().st_mtime_ns
                except OSError:
                    continue
    return snapshot


def _newest_generated_image(before: dict[Path, int]) -> Path | None:
    candidates: list[Path] = []
    for directory in _candidate_generated_dirs():
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_OUTPUT_SUFFIXES:
                continue
            try:
                resolved = path.resolve()
                mtime = path.stat().st_mtime_ns
            except OSError:
                continue
            if resolved not in before or mtime > before[resolved]:
                candidates.append(path)
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.stat().st_mtime_ns)


def _path_from_output(output: str) -> Path | None:
    for line in output.splitlines():
        text = line.strip().strip('"').strip("'")
        if not text:
            continue
        path = Path(text)
        if path.exists() and path.is_file() and path.suffix.lower() in SUPPORTED_OUTPUT_SUFFIXES:
            return path
    return None


def _looks_like_procedural_fallback(text: str) -> bool:
    lowered = text.lower()
    markers = [
        "from pil",
        "imagedraw",
        "image.new(",
        "image.effect_noise",
        "python -",
        "python.exe",
        "<svg",
        "savefig(",
    ]
    return any(marker in lowered for marker in markers)


def _short_reason(text: str, limit: int = 1600) -> str:
    compact = "\n".join(line.rstrip() for line in text.splitlines() if line.strip())
    if len(compact) <= limit:
        return compact
    timeout_lines = [line for line in compact.splitlines() if "Timed out after" in line]
    if timeout_lines:
        prefix = timeout_lines[-1]
        remaining = max(200, limit - len(prefix) - 80)
        return (
            f"{prefix}\n"
            f"{compact[:remaining].rstrip()}... "
            "[truncated; see _worker-logs for full output]"
        )
    return compact[:limit].rstrip() + "... [truncated; see _worker-logs for full output]"


def _copy_as_png_source(source: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if source.resolve() == output.resolve():
        return
    shutil.copy2(source, output)


def _candidate_generated_dirs() -> list[Path]:
    candidates: list[Path] = []
    explicit = os.environ.get("BOOK_TO_COMIC_GENERATED_IMAGES_DIR")
    if explicit:
        candidates.append(Path(explicit))
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        candidates.append(Path(codex_home) / "generated_images")
    candidates.append(Path.home() / ".codex" / "generated_images")
    return _dedupe(candidates)


def _resolve_command(command: str) -> str | None:
    path = Path(command)
    if path.exists():
        return str(path)
    return shutil.which(command)


def _dedupe(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result
