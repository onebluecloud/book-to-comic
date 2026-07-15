"""Content-based image admission control for externally supplied files.

Every image that enters the project from outside (host generation results,
inbox drops, refine imports) used to be trusted by file EXTENSION only, while
Pillow decodes by CONTENT — a PSD or FITS payload renamed to .png decoded with
the vulnerable codepaths anyway (release audit v5.13.1 P1-6, Pillow
GHSA-pwv6-vv43-88gr / GHSA-whj4-6x5x-4v2j). This module is the single choke
point: format allowlist, byte-size cap, pixel cap, and decompression-bomb
escalation to a hard error.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ALLOWED_FORMATS: tuple[str, ...] = ("PNG", "JPEG", "WEBP")
# Generous for comic panels (a 1536x2048 panel is ~3.1MP); anything past this
# is not a panel, it is a resource-exhaustion attempt or a mistake.
MAX_PIXELS = 80_000_000
MAX_FILE_BYTES = 60 * 1024 * 1024


def open_image_checked(path: str | Path, *, purpose: str = "image") -> tuple[int, int, str]:
    """Validate an external image file; return (width, height, format).

    Rejects: files over MAX_FILE_BYTES, content that is not PNG/JPEG/WEBP
    (whatever the extension claims), pixel counts over MAX_PIXELS, and
    undecodable payloads. Raises ValueError with an actionable message.
    """
    source = Path(path)
    size = source.stat().st_size
    if size > MAX_FILE_BYTES:
        raise ValueError(
            f"{purpose} is too large: {source.name} ({size} bytes > {MAX_FILE_BYTES}). "
            "Panels never need files this big — re-export it."
        )
    try:
        with Image.open(source, formats=list(ALLOWED_FORMATS)) as image:
            width, height = image.size
            detected = str(image.format or "")
            if width * height > MAX_PIXELS:
                raise ValueError(
                    f"{purpose} exceeds the pixel budget: {source.name} is {width}x{height} "
                    f"({width * height} px > {MAX_PIXELS}). Refusing to decode a potential decompression bomb."
                )
            image.verify()
    except Image.DecompressionBombError as exc:
        raise ValueError(f"{purpose} looks like a decompression bomb: {source.name} ({exc})") from exc
    except Image.UnidentifiedImageError as exc:
        raise ValueError(
            f"{purpose} content is not PNG/JPEG/WEBP (extensions are not trusted): {source.name}. "
            "Re-export the image as a real PNG/JPEG/WEBP."
        ) from exc
    return width, height, detected
