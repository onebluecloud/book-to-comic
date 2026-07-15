"""Book-to-Comic layout MCP server — the "domestic" leg.

This exposes ONLY the quick comic layout step (panel images + captions ->
DRAFT-tier comic layout, no quality/rights gates) as an MCP tool, so any MCP
client — Cherry Studio with a Doubao key, Claude Code, Codex — can call it
after generating the panels with whatever image model it has. Draft output
must not be published as an official deliverable; the gated path is the Codex
skill's init-project → validate-* → compose-project flow.

It is a separate, optional entry point. It does NOT touch the Codex skill flow
(SKILL.md / init-project / check / compose); it just reuses the same layout
core (quick_comic). The Codex leg keeps working exactly as before.

Run:         python -m book_to_comic.mcp_server
Dependency:  pip install "book-to-comic[mcp]"   (adds the `mcp` package)
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from .quick import quick_comic

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - only hit when extra not installed
    raise SystemExit(
        'The MCP server needs the `mcp` package. Install it with:\n'
        '    pip install "book-to-comic[mcp]"\n'
        "(this is only for the domestic / Cherry Studio leg; the Codex skill does not need it.)"
    ) from exc


mcp = FastMCP("book-to-comic")


@mcp.tool()
def render_comic_draft(
    images_dir: str,
    captions: str,
    title: str = "漫画",
    style: str = "ink-sketch",
) -> str:
    """把一组分镜图 + 文案排成**草稿级**漫画版式（长图 / 轮播卡 / 封面 / PDF）。

    在生图工具(如豆包 Seedream)逐格出图、存到同一个文件夹后调用本工具。
    注意：这是 quick 快速排版，**不跑任何质量/权利闸门**（gates=none），
    产物属草稿级，不能当正式成品直接公开发布；正式流程请走 Codex skill 的
    init-project → 各 validate 闸 → compose-project。

    Args:
        images_dir: 存放分镜图的文件夹,每格一张(文件名随意,按自然顺序排序)。
        captions: 每格一段文案,段与段之间用单独一行 `---` 分隔,顺序对应每张图。
        title: 封面和页眉上显示的标题。
        style: 叠字/版式风格,可选 ink-sketch / manhua / manga / webtoon-manhwa /
            editorial / franco-belgian-bd / comic-strip / doodle / retro-halftone。

    Returns:
        一段说明文字,列出长图 / 卡片目录 / 封面 / PDF 的输出路径,并标注草稿级。
    """
    # Unique temp file + guaranteed cleanup: the old fixed-name file lingered
    # in the system temp dir and collided across calls (audit P2-4).
    captions_fd = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", prefix="book-to-comic-captions-", suffix=".txt", delete=False
    )
    captions_file = Path(captions_fd.name)
    try:
        with captions_fd:
            captions_fd.write(captions)
        result = quick_comic(images_dir, captions_file, title=title, style_id=style)
    finally:
        captions_file.unlink(missing_ok=True)
    return (
        f"草稿级漫画排版完成（{result['panel_count']} 格，pipeline_tier={result.get('pipeline_tier', 'draft')}，"
        f"gates={result.get('gates', 'none')}——未过任何质量/权利闸，不可当正式成品公开发布）：\n"
        f"- 长图：{result['comic_long']}\n"
        f"- 卡片：{result['cards_dir']}（{result['card_count']} 张）\n"
        f"- 封面：{result['cover']}\n"
        f"- PDF：{result['pdf']}"
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
