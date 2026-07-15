from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from .image_backends import probe_image_backends


def detect_capabilities() -> dict[str, object]:
    """Report deterministic local capabilities without probing model providers."""
    image_backend_report = probe_image_backends()
    return {
        "filesystem": True,
        "web_search": "host|browser|cli|none",
        "host_image_generation": "host-orchestrated; requires saved PNG round-trip",
        "host_image_batch_adapter": _host_image_batch_adapter(image_backend_report),
        "host_image_roundtrip_required": True,
        "host_image_import": True,
        "final_image_backend_ready": image_backend_report["final_backend_ready"],
        "selected_final_image_backend": image_backend_report["selected_backend"],
        "python": True,
        "python_executable": Path(sys.executable).name,
        "local_ocr": shutil.which("tesseract") is not None,
        "local_image_model": _has_local_image_endpoint(),
        "external_api_enabled": False,
        "high_quality_gate": "inbox-prepare/inbox-import (official no-host-image fallback; candidates then approve-asset)",
        "vector_quality_tier": "draft-fallback",
    }


def capabilities_json() -> str:
    return json.dumps(detect_capabilities(), ensure_ascii=False, indent=2) + "\n"


def _has_local_image_endpoint() -> bool:
    return any(
        shutil.which(command) is not None
        for command in ("comfy", "comfyui", "automatic1111", "a1111")
    )


def _host_image_batch_adapter(image_backend_report: dict[str, object]) -> str:
    selected = image_backend_report.get("selected_backend")
    if selected:
        return str(selected)
    return "blocked; no save-capable PNG backend passed saved-PNG image self-test"
