"""Cross-platform CJK font resolution for comic lettering.

The DISTRIBUTED skill package does NOT bundle a font binary: Noto Sans SC is
~18MB and publishing platforms cap single files at 10MB, so ``assets/fonts/``
ships only the OFL license text and a README. Resolution falls back to the CJK
fonts every mainstream OS already has (msyh on Windows, PingFang on macOS,
Noto CJK on Linux). Consequence stated honestly: exact glyph metrics — line
wrapping, balloon sizing — can differ slightly between machines. For
pixel-identical output across machines, drop any OFL CJK font into
``assets/fonts/`` or point ``BOOK_TO_COMIC_FONT`` at one.

Resolution order (first hit wins):
1. ``BOOK_TO_COMIC_FONT``        explicit font file path
2. ``BOOK_TO_COMIC_FONT_DIR``    a directory to search first
3. ``assets/fonts/``             a font the user dropped in (none by default)
4. system font directories       Windows / macOS / Linux
5. recursive search of the above (Linux Noto lives in nested subdirs)
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

# Bundled open-licensed CJK font. fonts.py lives in book_to_comic/, so the
# package root (which holds assets/) is one level up.
_BUNDLED_FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
BUNDLED_REGULAR = "NotoSansSC-VF.ttf"

# Cross-platform CJK font filenames. The bundled Noto file is first so a clean
# install always resolves to it; the rest cover fonts already present on each OS.
_REGULAR_CANDIDATES: tuple[str, ...] = (
    BUNDLED_REGULAR,
    # Windows
    "msyh.ttc", "msyh.ttf", "simhei.ttf", "simsun.ttc", "Deng.ttf",
    # macOS
    "PingFang.ttc", "Hiragino Sans GB.ttc", "Songti.ttc", "STHeiti Light.ttc",
    "Arial Unicode.ttf",
    # Linux (Noto CJK / Source Han / WenQuanYi / Droid)
    "NotoSansCJK-Regular.ttc", "NotoSansCJKsc-Regular.otf",
    "NotoSansSC-Regular.otf", "NotoSansSC-Regular.ttf",
    "SourceHanSansSC-Regular.otf", "SourceHanSansCN-Regular.otf",
    "wqy-zenhei.ttc", "wqy-microhei.ttc",
    "DroidSansFallbackFull.ttf", "DroidSansFallback.ttf",
)

_BOLD_CANDIDATES: tuple[str, ...] = (
    # Prefer a real bold face when present, else fall back to the bundled VF.
    "msyhbd.ttc", "msyhbd.ttf", "simhei.ttf",
    "NotoSansCJK-Bold.ttc", "NotoSansSC-Bold.otf", "SourceHanSansSC-Bold.otf",
    "PingFang.ttc",
    BUNDLED_REGULAR,
)


def _system_font_dirs() -> list[Path]:
    home = Path.home()
    return [
        # Windows
        Path("C:/Windows/Fonts"),
        # macOS
        Path("/System/Library/Fonts"),
        Path("/System/Library/Fonts/Supplemental"),
        Path("/Library/Fonts"),
        home / "Library" / "Fonts",
        # Linux
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        home / ".fonts",
        home / ".local" / "share" / "fonts",
    ]


def _search_dirs() -> list[Path]:
    dirs: list[Path] = []
    env_dir = os.environ.get("BOOK_TO_COMIC_FONT_DIR")
    if env_dir:
        dirs.append(Path(env_dir))
    dirs.append(_BUNDLED_FONT_DIR)  # bundled Noto first -> zero-config cross-platform
    dirs.extend(_system_font_dirs())
    return dirs


@lru_cache(maxsize=16)
def find_cjk_font(weight: str = "regular", extra_candidates: tuple[str, ...] = ()) -> Path:
    """Return a path to a usable CJK font.

    ``extra_candidates`` are tried before the built-in per-weight list, so a
    caller can express a preferred face while still inheriting cross-platform
    fallbacks. Raises ``FileNotFoundError`` with actionable guidance if nothing
    is found.
    """
    explicit = os.environ.get("BOOK_TO_COMIC_FONT")
    if explicit and Path(explicit).is_file():
        return Path(explicit)

    base = _BOLD_CANDIDATES if weight == "bold" else _REGULAR_CANDIDATES
    candidates = tuple(dict.fromkeys((*extra_candidates, *base)))  # dedupe, keep order
    dirs = _search_dirs()

    # Fast path: direct filename hits.
    for font_dir in dirs:
        for name in candidates:
            path = font_dir / name
            if path.is_file():
                return path

    # Fallback: recursive search (Linux Noto lives under nested subdirectories
    # such as /usr/share/fonts/opentype/noto/).
    for font_dir in dirs:
        if not font_dir.is_dir():
            continue
        for name in candidates:
            for hit in font_dir.rglob(name):
                if hit.is_file():
                    return hit

    raise FileNotFoundError(
        "No CJK font found for Chinese lettering. The bundled "
        f"assets/fonts/{BUNDLED_REGULAR} appears to be missing. Fix by either: "
        "(1) reinstalling the skill so the bundled font is present; "
        "(2) setting BOOK_TO_COMIC_FONT=/absolute/path/to/a/cjk-font.ttf; or "
        "(3) installing a CJK font such as Noto Sans CJK. "
        f"Searched: {', '.join(str(d) for d in dirs)}"
    )


def load_variant(
    path: str | Path,
    size: int,
    weight: str = "regular",
) -> ImageFont.FreeTypeFont:
    """Load a font at ``size``, pinning the weight for variable fonts.

    The bundled Noto files are variable fonts whose default instance is Thin,
    which renders far too light for comic lettering. When the resolved file
    exposes a weight axis we pin it (400 regular / 700 bold). Static fonts such
    as the Windows ``msyh.ttc``/``msyhbd.ttc`` pair have no axis, so they are
    used as-is and the caller's regular/bold file choice already carries weight.
    """
    font = ImageFont.truetype(str(path), int(size))
    try:
        axes = font.get_variation_axes()
    except (OSError, AttributeError):
        axes = None
    if axes:
        try:
            font.set_variation_by_axes([700 if weight == "bold" else 400])
        except (OSError, ValueError):
            pass
    return font
