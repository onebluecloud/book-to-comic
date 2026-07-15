from pathlib import Path

from .models import AdaptationPackage, Character, Panel
from .styles import get_style


def export_manual_prompt_files(
    package: AdaptationPackage,
    output_dir: str | Path,
    style_id: str | None = None,
) -> list[Path]:
    style = get_style(style_id or package.style_id)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    written.append(_write(destination / "00-character-reference.txt", _character_reference_prompt(package, style.prompt_spec)))
    for panel in package.storyboard:
        written.append(_write(destination / f"{panel.index:02d}-panel.txt", _panel_prompt(panel, package.characters, style.prompt_spec)))
    written.append(_write(destination / "overlay-text.md", _overlay_text(package)))
    return written


def _write(path: Path, text: str) -> Path:
    path.write_text(text.strip() + "\n", encoding="utf-8")
    return path


def _character_reference_prompt(package: AdaptationPackage, style_prompt: str) -> str:
    return "\n".join(
        [
            style_prompt,
            "",
            "Scene: character reference sheet for the recurring cast; full-body simple poses, neutral background.",
            "No speech bubbles. No readable text, letters, numbers, or pseudo-text.",
            "Lock clothing, skin tone, face, glasses, shoes, body proportions, and color ownership.",
            "Pose safety: adult ordinary proportions, natural readable limbs and hands, no warped anatomy, no extreme foreshortening, no mascot proportions.",
            "Colors belong to clothing, not skin. do not redesign the characters.",
            "",
            "Characters:",
            _character_lines(package.characters),
        ]
    )


def _panel_prompt(panel: Panel, characters: tuple[Character, ...], style_prompt: str) -> str:
    lines = [
        "Do not generate this panel unless the approved 00-character-reference image is attached as an input/reference image.",
        "If a user-approved reference already exists, use that exact image; do not regenerate or improve the character design.",
        "Use the same reference image for character consistency.",
        "Character lock: do not redesign the characters; do not change clothing, skin tone, body proportions, face, glasses, shoes, badge, or color ownership.",
        "Pose safety: adult ordinary proportions, natural readable limbs and hands, no warped anatomy, no extreme foreshortening, no mascot proportions.",
        "Colors belong to clothing, not skin.",
        style_prompt,
        "",
        "Characters:",
        _character_lines(characters),
        "",
        f"Scene: {panel.visual}",
        "Text handling: no readable text, letters, numbers, prices, equations, or pseudo-text in the generated image.",
        "Full-bleed: the artwork must fill the entire canvas edge to edge — no borders, no frame lines, no mats, no letterboxing or flat margins.",
        "Do not draw empty white rectangles, labels, tags, cards, signboards, UI screens, price stickers, text placeholders, or reserved text areas.",
        "Use objects, gestures, icons, anchors, carts, shelves, stamps, and character acting to express the idea instead of any text container.",
        "Do not draw speech bubbles. Do not draw caption boxes, bottom narration frames, large white text areas, or end-hook panels.",
        "Narration is added later in the final layout, outside the generated panel art; dialogue and hooks are also added there.",
    ]
    return "\n".join(lines)


def _overlay_text(package: AdaptationPackage) -> str:
    lines = [f"# {package.episode_title} 叠字文本", ""]
    for panel in package.storyboard:
        lines.extend([f"## 第 {panel.index} 格 · {panel.beat}"])
        for dialogue in panel.dialogue:
            lines.append(f"- 台词：{dialogue}")
        if panel.narration:
            lines.append(f"- 旁白：{panel.narration}")
        if panel.comment_hook:
            lines.append(f"- 撩评论：{panel.comment_hook}")
        lines.append("")
    return "\n".join(lines)


def _character_lines(characters: tuple[Character, ...]) -> str:
    return "\n".join(f"- {character.prompt_fragment}" for character in characters)
