from __future__ import annotations

from html import escape
from pathlib import Path
import json
import re
import uuid
import zipfile

from PIL import Image


DELIVERY_FORMATS = ("pdf", "cbz", "epub", "zip-production")


def export_cards_delivery(
    cards_dir: str | Path,
    output_path: str | Path,
    delivery_format: str,
    title: str = "comic",
    language: str = "zh-CN",
) -> Path:
    cards = _ordered_card_paths(Path(cards_dir))
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    if delivery_format == "pdf":
        _write_pdf(cards, output)
    elif delivery_format == "cbz":
        _write_cbz(cards, output)
    elif delivery_format == "epub":
        _write_epub(cards, output, title=title, language=language)
    elif delivery_format == "zip-production":
        # This low-level export never runs the gates. It must not be able to
        # mint an archive that looks like a gated production bundle (release
        # audit v5.13.2 P0-3): real production*.zip files come ONLY from
        # compose-project.
        from .delivery_gate import BUNDLE_NAMES

        if output.name in BUNDLE_NAMES:
            raise ValueError(
                f"{output.name} is reserved for gated compose-project output. This export runs no "
                "gates — name it draft-pack.zip (or anything else) instead."
            )
        _write_production_zip(cards, output, title=title)
    else:
        raise ValueError(f"Unsupported delivery format: {delivery_format}")
    return output


def _ordered_card_paths(cards_dir: Path) -> list[Path]:
    if not cards_dir.exists():
        raise FileNotFoundError(f"Cards directory does not exist: {cards_dir}")
    cards = sorted((path for path in cards_dir.glob("*.png") if path.is_file()), key=_natural_key)
    if not cards:
        raise FileNotFoundError(f"No PNG cards found in {cards_dir}")
    return cards


def _natural_key(path: Path) -> tuple[object, ...]:
    parts = re.split(r"(\d+)", path.stem)
    key: list[object] = []
    for part in parts:
        if part.isdigit():
            key.append(int(part))
        else:
            key.append(part.lower())
    key.append(path.suffix.lower())
    return tuple(key)


def _write_pdf(cards: list[Path], output: Path) -> None:
    images: list[Image.Image] = []
    try:
        for path in cards:
            images.append(Image.open(path).convert("RGB"))
        first, rest = images[0], images[1:]
        first.save(output, "PDF", save_all=True, append_images=rest, resolution=100.0)
    finally:
        for image in images:
            image.close()


def _write_cbz(cards: list[Path], output: Path) -> None:
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in cards:
            archive.write(path, path.name)


def _write_epub(cards: list[Path], output: Path, title: str, language: str = "zh-CN") -> None:
    image_sizes = _image_sizes(cards)
    safe_title = escape(title)
    safe_language = escape(language or "zh-CN")
    book_id = f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, title + ':' + ','.join(path.name for path in cards))}"

    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
""",
            compress_type=zipfile.ZIP_DEFLATED,
        )
        archive.writestr("OEBPS/content.opf", _epub_content_opf(cards, image_sizes, safe_title, book_id, safe_language))
        archive.writestr("OEBPS/nav.xhtml", _epub_nav(cards, safe_title, safe_language))
        archive.writestr("OEBPS/styles.css", _epub_css())
        for index, (path, (width, height)) in enumerate(zip(cards, image_sizes), start=1):
            archive.write(path, f"OEBPS/images/{path.name}", compress_type=zipfile.ZIP_DEFLATED)
            archive.writestr(
                f"OEBPS/pages/page-{index:03d}.xhtml",
                _epub_page(index, path.name, width, height, safe_title, safe_language),
                compress_type=zipfile.ZIP_DEFLATED,
            )


def _image_sizes(cards: list[Path]) -> list[tuple[int, int]]:
    sizes: list[tuple[int, int]] = []
    for path in cards:
        with Image.open(path) as image:
            sizes.append(image.size)
    return sizes


def _epub_content_opf(cards: list[Path], image_sizes: list[tuple[int, int]], safe_title: str, book_id: str, safe_language: str = "zh-CN") -> str:
    image_items = "\n".join(
        f'    <item id="img{index:03d}" href="images/{escape(path.name)}" media-type="image/png"/>'
        for index, path in enumerate(cards, start=1)
    )
    page_items = "\n".join(
        f'    <item id="page{index:03d}" href="pages/page-{index:03d}.xhtml" media-type="application/xhtml+xml" properties="svg"/>'
        for index in range(1, len(cards) + 1)
    )
    spine_items = "\n".join(f'    <itemref idref="page{index:03d}"/>' for index in range(1, len(cards) + 1))
    first_width, first_height = image_sizes[0]
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<package version="3.0" unique-identifier="bookid" xmlns="http://www.idpf.org/2007/opf">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">{escape(book_id)}</dc:identifier>
    <dc:title>{safe_title}</dc:title>
    <dc:language>{safe_language}</dc:language>
    <meta property="rendition:layout">pre-paginated</meta>
    <meta property="rendition:orientation">portrait</meta>
    <meta property="rendition:spread">none</meta>
    <meta name="cover" content="img001"/>
    <meta name="fixed-layout" content="true"/>
    <meta name="original-resolution" content="{first_width}x{first_height}"/>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="css" href="styles.css" media-type="text/css"/>
{image_items}
{page_items}
  </manifest>
  <spine page-progression-direction="ltr">
{spine_items}
  </spine>
</package>
"""


def _epub_nav(cards: list[Path], safe_title: str, safe_language: str = "zh-CN") -> str:
    items = "\n".join(
        f'      <li><a href="pages/page-{index:03d}.xhtml">Page {index}</a></li>'
        for index in range(1, len(cards) + 1)
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="{safe_language}" xml:lang="{safe_language}">
  <head>
    <title>{safe_title}</title>
  </head>
  <body>
    <nav epub:type="toc" id="toc">
      <h1>{safe_title}</h1>
      <ol>
{items}
      </ol>
    </nav>
  </body>
</html>
"""


def _epub_page(index: int, image_name: str, width: int, height: int, safe_title: str, safe_language: str = "zh-CN") -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" lang="{safe_language}" xml:lang="{safe_language}">
  <head>
    <title>{safe_title} - Page {index}</title>
    <meta name="viewport" content="width={width}, height={height}"/>
    <link rel="stylesheet" type="text/css" href="../styles.css"/>
  </head>
  <body>
    <main>
      <svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" preserveAspectRatio="xMidYMid meet">
        <image href="../images/{escape(image_name)}" width="{width}" height="{height}"/>
      </svg>
    </main>
  </body>
</html>
"""


def _epub_css() -> str:
    return """html, body {
  margin: 0;
  padding: 0;
  width: 100%;
  height: 100%;
  background: #11100d;
}
main {
  margin: 0;
  padding: 0;
}
svg {
  display: block;
  width: 100%;
  height: 100vh;
}
"""


def _write_production_zip(cards: list[Path], output: Path, title: str) -> None:
    manifest = {
        "title": title,
        "format": "zip-production",
        # Honest tier declaration: this pack bypasses every deterministic and
        # LLM gate, so it can never present itself as a gated deliverable.
        "bundle": "draft",
        "gates": "none",
        "card_count": len(cards),
        "cards": [f"cards/{path.name}" for path in cards],
    }
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        for path in cards:
            archive.write(path, f"cards/{path.name}")
