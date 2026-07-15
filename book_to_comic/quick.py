"""Quick comic: turn a folder of images + a captions file into a finished comic.

This is the "domestic AI" path. It does NOT need an agent, a project, planning
JSON, or any of the validate-* gates. A human directs the creative work in any
chat AI (e.g. Doubao writes the storyboard + captions and generates the images),
then runs ONE command here to letter, lay out, cover and export.

Inputs:
- images_dir: a folder with one image per panel (any names; sorted naturally).
- captions_file: one caption block per panel, separated by a line of `---`
  (or by blank lines). The number of blocks must equal the number of images.

Outputs (under out_dir):
- comic-long.png         vertical long image (good for Xiaohongshu / WeChat)
- cards/01.png ...       1080x1440 carousel cards
- cover.png              a simple cover from panel 1 + title
- comic.pdf              a PDF of the cards
- comic.cbz              a comic-reader archive of the cards
- comic.epub             a fixed-layout EPUB of the cards
- draft-pack.zip         a DRAFT archive with ordered cards (no gates; not a public bundle)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from .composer import compose_carousel_card_images, compose_long_image
from .delivery import export_cards_delivery
from .fonts import find_cjk_font, load_variant
from .models import AdaptationPackage, Panel, Suitability

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def _natural_key(path: Path) -> tuple[object, ...]:
    parts = re.split(r"(\d+)", path.stem)
    key: list[object] = [int(p) if p.isdigit() else p.lower() for p in parts]
    return tuple(key)


def parse_captions(text: str) -> list[str]:
    """Split a captions file into one block per panel.

    Primary separator is a line of three or more dashes (`---`). If none is
    present, fall back to blank-line separation.
    """
    if re.search(r"(?m)^\s*-{3,}\s*$", text):
        blocks = re.split(r"(?m)^\s*-{3,}\s*$", text)
    else:
        blocks = re.split(r"\n\s*\n", text)
    return [block.strip() for block in blocks if block.strip()]


def _ordered_images(images_dir: Path) -> list[Path]:
    return sorted(
        (p for p in images_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES),
        key=_natural_key,
    )


def _normalize_images(image_paths: list[Path], panel_dir: Path) -> None:
    from .image_safety import open_image_checked

    panel_dir.mkdir(parents=True, exist_ok=True)
    for index, source in enumerate(image_paths, start=1):
        # Draft or not, external images go through the same content-based
        # admission (release audit v5.13.2 P1-6: a BMP renamed .png decoded
        # here happily).
        open_image_checked(source, purpose="quick draft image")
        with Image.open(source) as image:
            rgb = image.convert("RGB")
            rgb.save(panel_dir / f"{index:02d}.png", "PNG")


def _build_package(title: str, captions: list[str], style_id: str) -> AdaptationPackage:
    storyboard = tuple(
        Panel(
            index=index,
            beat="",
            visual="",
            dialogue=(),
            narration=caption,
            card_copy=(caption,),
        )
        for index, caption in enumerate(captions, start=1)
    )
    return AdaptationPackage(
        book_title=title,
        author="",
        episode_title=title,
        suitability=Suitability(is_applicable=True, category="quick", reason="quick mode"),
        covered_points=(),
        core_ideas=(),
        methods=(),
        light_shell="",
        hard_core="",
        characters=(),
        character_relationship="",
        storyboard=storyboard,
        title_candidates=(title,),
        style_id=style_id,
    )


def _make_cover(first_panel: Path, title: str, output: Path, width: int = 1080, height: int = 1440) -> Path:
    with Image.open(first_panel) as image:
        art = image.convert("RGB")
    # cover-fill the panel into width x height
    scale = max(width / art.width, height / art.height)
    resized = art.resize((max(1, int(art.width * scale)), max(1, int(art.height * scale))))
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    canvas = resized.crop((left, top, left + width, top + height))

    draw = ImageDraw.Draw(canvas, "RGBA")
    # darken the bottom band for legible title
    band_top = int(height * 0.62)
    draw.rectangle((0, band_top, width, height), fill=(0, 0, 0, 150))
    title_font = load_variant(
        find_cjk_font(weight="bold", extra_candidates=("NotoSerifSC-VF.ttf", "msyhbd.ttc", "simhei.ttf")),
        int(width * 0.085),
        "bold",
    )
    draw.text((int(width * 0.07), int(height * 0.72)), title, font=title_font, fill=(245, 224, 168))
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, "PNG")
    return output


def quick_comic(
    images_dir: str | Path,
    captions_file: str | Path,
    *,
    title: str = "漫画",
    style_id: str = "ink-sketch",
    out_dir: str | Path | None = None,
) -> dict[str, Any]:
    images_dir = Path(images_dir)
    if not images_dir.is_dir():
        raise FileNotFoundError(f"Images folder not found: {images_dir}")
    image_paths = _ordered_images(images_dir)
    if not image_paths:
        raise ValueError(f"No images found in {images_dir} (looked for .png/.jpg/.jpeg/.webp).")

    captions = parse_captions(Path(captions_file).read_text(encoding="utf-8"))
    if len(captions) != len(image_paths):
        raise ValueError(
            f"图和文案数量对不上:找到 {len(image_paths)} 张图,但文案有 {len(captions)} 段。\n"
            f"请让两者一样多(每格一张图 + 一段文案,文案之间用一行 --- 分隔)。"
        )

    out = Path(out_dir) if out_dir else images_dir.parent / f"{images_dir.name}-comic"
    panel_dir = out / "panels"
    final = out / "final"
    final.mkdir(parents=True, exist_ok=True)
    _normalize_images(image_paths, panel_dir)

    package = _build_package(title, captions, style_id)
    long_image = compose_long_image(
        package, final / "comic-long.png", panel_dir=panel_dir, width=1080, require_panels=True, text_mode="long_form"
    )
    cards = compose_carousel_card_images(package, panel_dir, final / "cards", width=1080, height=1440)
    cover = _make_cover(panel_dir / "01.png", title, final / "cover.png")
    pdf = export_cards_delivery(final / "cards", final / "comic.pdf", "pdf", title=title)
    cbz = export_cards_delivery(final / "cards", final / "comic.cbz", "cbz", title=title)
    epub = export_cards_delivery(final / "cards", final / "comic.epub", "epub", title=title)
    # Named draft-pack, not production: a no-gates output must not carry the
    # public bundle's filename (audit P2-5 / P0-5).
    production_zip = export_cards_delivery(final / "cards", final / "draft-pack.zip", "zip-production", title=title)

    import json

    # quick is the explicit no-gates path. Say so in machine-readable form so a
    # quick output can never masquerade as a gated formal delivery (P0-1).
    tier_note = {
        "schema_version": "1.0",
        "pipeline_tier": "draft",
        "gates": "none",
        "note": "quick path: no planning, no QA gates. For a formal gated delivery use the project pipeline (init-project ... compose-project).",
    }
    (final / "pipeline-tier.json").write_text(
        json.dumps(tier_note, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    return {
        "out_dir": str(out),
        "pipeline_tier": "draft",
        "gates": "none",
        "panel_count": len(image_paths),
        "comic_long": str(long_image),
        "cards_dir": str(final / "cards"),
        "card_count": len(cards),
        "cover": str(cover),
        "pdf": str(pdf),
        "cbz": str(cbz),
        "epub": str(epub),
        "production_zip": str(production_zip),
        "zip": str(production_zip),
    }
