from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any


DEFAULT_TOOLS_DIR = Path(
    os.environ.get("BOOK_TO_COMIC_TOOLS_DIR") or (Path.home() / ".book-to-comic" / "tools")
)
# Pinned: an auto-download that floats `latest` executes whatever npm serves
# that day (audit P2-6). Bump deliberately (env override for newer builds);
# 0.144.1 was the registry latest when this pin was set (2026-07-12).
CODEX_PACKAGE = os.environ.get("BOOK_TO_COMIC_CODEX_PACKAGE") or "@openai/codex@0.144.1"
# Auto-install only runs when the user explicitly opts in — a library quietly
# running npm install is supply-chain surface, not a convenience.
INSTALL_OPT_IN_ENV = "BOOK_TO_COMIC_ALLOW_NPM_INSTALL"


@dataclass
class CodexCliCandidate:
    path: str
    source: str
    status: str
    launchable: bool
    reason: str = ""
    version: str = ""


@dataclass
class CodexCliBootstrapReport:
    schema_version: str
    launchable: bool
    selected_bin: str | None
    installed: bool
    install_attempted: bool
    install_status: str
    tools_dir: str
    candidates: list[CodexCliCandidate] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["candidates"] = [asdict(item) for item in self.candidates]
        return data


def ensure_codex_cli(
    *,
    install: bool = False,
    tools_dir: str | Path | None = None,
    codex_bin: str | None = None,
    timeout_seconds: int = 12,
    install_timeout_seconds: int = 300,
) -> dict[str, object]:
    """Find or install a launchable Codex CLI outside WindowsApps.

    The Windows Store/AppX Codex binary can appear on PATH while still being
    blocked for child-process launches. For worker automation we need a normal
    executable path, usually the npm-installed `codex.cmd` wrapper.
    """
    root = Path(tools_dir) if tools_dir else Path(os.environ.get("BOOK_TO_COMIC_TOOLS_DIR", DEFAULT_TOOLS_DIR))
    candidates = _probe_candidates(root, explicit_bin=codex_bin, timeout_seconds=timeout_seconds)
    selected = next((item.path for item in candidates if item.launchable), None)
    report = CodexCliBootstrapReport(
        schema_version="1.0",
        launchable=selected is not None,
        selected_bin=selected,
        installed=False,
        install_attempted=False,
        install_status="skipped",
        tools_dir=str(root),
        candidates=candidates,
        notes=[
            "WindowsApps Codex paths are treated as blocked unless they actually launch.",
            "A normal npm/standalone Codex CLI path is required for codex-exec-image-worker.",
        ],
    )
    if selected or not install or codex_bin:
        return report.to_dict()

    if os.environ.get(INSTALL_OPT_IN_ENV) != "1":
        report.install_status = "refused"
        report.notes.append(
            f"Automatic npm install is opt-in: set {INSTALL_OPT_IN_ENV}=1 to allow installing "
            f"{CODEX_PACKAGE} under {root / 'codex-cli'}, or install Codex CLI yourself and pass --codex-bin."
        )
        _write_bootstrap_report(root, report.to_dict())
        return report.to_dict()

    install_result = _install_with_npm(root, timeout_seconds=install_timeout_seconds)
    report.install_attempted = True
    report.install_status = install_result["status"]
    report.installed = install_result["status"] == "ok"
    if install_result.get("message"):
        report.notes.append(str(install_result["message"]))

    candidates = _probe_candidates(root, explicit_bin=None, timeout_seconds=timeout_seconds)
    selected = next((item.path for item in candidates if item.launchable), None)
    report.candidates = candidates
    report.launchable = selected is not None
    report.selected_bin = selected
    _write_bootstrap_report(root, report.to_dict())
    return report.to_dict()


def default_managed_codex_bin(tools_dir: str | Path | None = None) -> Path:
    root = Path(tools_dir) if tools_dir else Path(os.environ.get("BOOK_TO_COMIC_TOOLS_DIR", DEFAULT_TOOLS_DIR))
    if os.name == "nt":
        return root / "codex-cli" / "node_modules" / ".bin" / "codex.cmd"
    return root / "codex-cli" / "node_modules" / ".bin" / "codex"


def _probe_candidates(root: Path, explicit_bin: str | None, timeout_seconds: int) -> list[CodexCliCandidate]:
    paths: list[tuple[str, str]] = []
    if explicit_bin:
        paths.append((explicit_bin, "explicit"))
        return [_probe_one(path, source=source, timeout_seconds=timeout_seconds) for path, source in paths]
    env_bin = os.environ.get("BOOK_TO_COMIC_CODEX_BIN")
    if env_bin:
        paths.append((env_bin, "BOOK_TO_COMIC_CODEX_BIN"))
    paths.append((str(default_managed_codex_bin(root)), "book-to-comic managed npm"))
    which_codex = shutil.which("codex")
    if which_codex:
        paths.append((which_codex, "PATH"))

    result: list[CodexCliCandidate] = []
    seen: set[str] = set()
    for path, source in paths:
        if not path or path in seen:
            continue
        seen.add(path)
        result.append(_probe_one(path, source=source, timeout_seconds=timeout_seconds))
    return result


def _probe_one(path: str, *, source: str, timeout_seconds: int) -> CodexCliCandidate:
    path_obj = Path(path)
    resolved = str(path_obj) if path_obj.exists() else shutil.which(path) or path
    if not Path(resolved).exists() and source != "PATH":
        return CodexCliCandidate(
            path=resolved,
            source=source,
            status="not-found",
            launchable=False,
            reason="candidate does not exist",
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
        return CodexCliCandidate(
            path=resolved,
            source=source,
            status="blocked",
            launchable=False,
            reason=str(exc),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CodexCliCandidate(
            path=resolved,
            source=source,
            status="blocked",
            launchable=False,
            reason=str(exc),
        )
    if completed.returncode != 0:
        return CodexCliCandidate(
            path=resolved,
            source=source,
            status="failed",
            launchable=False,
            reason=(completed.stderr.strip() or completed.stdout.strip())[:500],
        )
    return CodexCliCandidate(
        path=resolved,
        source=source,
        status="ok",
        launchable=True,
        version=(completed.stdout.strip() or completed.stderr.strip()),
    )


def _install_with_npm(root: Path, timeout_seconds: int) -> dict[str, object]:
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        return {"status": "failed", "message": "npm was not found; cannot install @openai/codex automatically"}
    install_prefix = root / "codex-cli"
    install_prefix.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    # Keep npm audit ON (audit P2-6): a bootstrap that both auto-downloads and
    # silences the auditor is the worst combination.
    command = [
        npm,
        "install",
        "--prefix",
        str(install_prefix),
        CODEX_PACKAGE,
        "--registry",
        "https://registry.npmjs.org/",
    ]
    try:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "failed", "message": f"npm install could not complete: {exc}"}
    if completed.returncode != 0:
        return {
            "status": "failed",
            "message": (completed.stderr.strip() or completed.stdout.strip())[-1200:],
        }
    return {"status": "ok", "message": f"Installed {CODEX_PACKAGE} under {install_prefix}"}


def _write_bootstrap_report(root: Path, report: dict[str, object]) -> Path:
    path = root / "codex-cli-bootstrap-report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
