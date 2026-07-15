from __future__ import annotations

import shutil
from pathlib import Path


SKILL_NAME = "book-to-comic"


# Working-tree noise that must not be installed as part of the skill.
# .agents/.claude matter twice over: they are host-config noise AND the
# default project-scope install DESTINATION lives inside them — without the
# ignore, installing from a source checkout recursively copied the install
# into itself until RecursionError (release audit v5.13.1 P0-5).
_INSTALL_IGNORE = {
    ".git", "__pycache__", "dist", "build", "tmp", ".pytest_cache", "tests", "node_modules",
    ".agents", ".claude", ".venv", "venv", ".mypy_cache", ".ruff_cache", ".idea", ".vscode",
    "outputs", "release",
}


def install_skill(
    target: str,
    scope: str = "project",
    project_dir: str | Path = ".",
    source_dir: str | Path | None = None,
) -> list[Path]:
    # The skill package IS the repository root (SKILL.md lives there). The old
    # default pointed at a nonexistent agent-skill/book-to-comic directory, so
    # install-skill failed on every machine (audit P2-1).
    source = Path(source_dir) if source_dir else Path(__file__).resolve().parents[1]
    if not (source / "SKILL.md").is_file():
        raise FileNotFoundError(
            f"Skill source not found: no SKILL.md under {source}. Run from a source checkout of the "
            "skill, or pass source_dir pointing at the directory that contains SKILL.md."
        )
    destinations = installation_destinations(target=target, scope=scope, project_dir=project_dir)
    for destination in destinations:
        copy_skill(source, destination)
    return destinations


def installation_destinations(target: str, scope: str, project_dir: str | Path = ".") -> list[Path]:
    if target not in {"codex", "claude", "both"}:
        raise ValueError(f"Unsupported target: {target}")
    if scope not in {"project", "user"}:
        raise ValueError(f"Unsupported scope: {scope}")
    project = Path(project_dir).resolve()
    targets = ("codex", "claude") if target == "both" else (target,)
    destinations: list[Path] = []
    for item in targets:
        if item == "codex":
            base = Path.home() / ".agents" / "skills" if scope == "user" else project / ".agents" / "skills"
        else:
            base = Path.home() / ".claude" / "skills" if scope == "user" else project / ".claude" / "skills"
        destinations.append(base / SKILL_NAME)
    return destinations


def copy_skill(source: Path, destination: Path) -> None:
    """Install via staging + atomic swap; never delete-before-copy.

    The old implementation rmtree'd the destination FIRST and had no
    source/destination overlap check, so re-installing from an already
    installed skill directory deleted the skill and then failed (release
    audit v5.13.1 P0-5).
    """
    if destination.name != SKILL_NAME:
        raise ValueError(f"Refusing to write a non-skill path: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_real = source.resolve()
    dest_real = destination.parent.resolve() / destination.name
    if dest_real == source_real:
        raise ValueError(
            f"Install destination {dest_real} IS the skill source — it is already a usable skill "
            "checkout; nothing to install. Pick a different scope/project-dir."
        )
    if dest_real in source_real.parents:
        raise ValueError(
            f"Refusing to install: destination {dest_real} contains the skill source {source_real} "
            "(copying a tree into its own ancestor)."
        )

    def ignore(_: str, names: list[str]) -> set[str]:
        return {
            name
            for name in names
            if name in _INSTALL_IGNORE or name.endswith(".pyc") or name.endswith(".pyo") or name.endswith(".zip")
        }

    staging = destination.parent / f".{destination.name}.staging"
    backup = destination.parent / f".{destination.name}.backup"
    for leftover in (staging, backup):
        if leftover.exists():
            shutil.rmtree(leftover)
    try:
        shutil.copytree(source, staging, ignore=ignore)
        _copy_runtime_package(staging)
        if not (staging / "SKILL.md").is_file() or not (staging / "book_to_comic" / "__init__.py").is_file():
            raise ValueError("Staged skill copy is incomplete (missing SKILL.md or runtime package); aborting install.")
        if destination.exists():
            destination.rename(backup)
        try:
            staging.rename(destination)
        except OSError:
            if backup.exists() and not destination.exists():
                backup.rename(destination)  # roll the old install back
            raise
        if backup.exists():
            shutil.rmtree(backup)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def _copy_runtime_package(destination: Path) -> None:
    runtime_source = Path(__file__).resolve().parent
    runtime_destination = destination / "book_to_comic"
    if runtime_destination.exists():
        shutil.rmtree(runtime_destination)

    def ignore(_: str, names: list[str]) -> set[str]:
        return {
            name
            for name in names
            if name == "__pycache__" or name.endswith(".pyc") or name.endswith(".pyo")
        }

    shutil.copytree(runtime_source, runtime_destination, ignore=ignore)
