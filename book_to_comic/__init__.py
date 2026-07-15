"""Host-native book-to-comic deterministic helpers."""

__version__ = "5.13.6"

from .engine import build_adaptation_prompt, build_sample_package, render_manual_package

__all__ = [
    "build_adaptation_prompt",
    "build_sample_package",
    "render_manual_package",
]
