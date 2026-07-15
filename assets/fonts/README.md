# Fonts

The distributed skill package does **not** bundle any font binaries — Chinese
lettering uses the CJK fonts every mainstream OS already ships (Windows 微软雅黑,
macOS 苹方, Linux Noto CJK). `book_to_comic/fonts.py` resolves them at run time
and pins weight 400 (regular) / 700 (bold) for variable fonts so text is never
rendered in a Thin instance.

Pixel-identical output across machines is optional: drop any open-licensed CJK
font into this directory (for example Noto Sans SC / Noto Serif SC, both under
the SIL OFL — see `OFL.txt`) and it takes priority over system fonts.

## Font discovery order (first hit wins)

1. `BOOK_TO_COMIC_FONT` — an explicit font file path;
2. `BOOK_TO_COMIC_FONT_DIR` — a directory searched first;
3. this directory (empty by default — user-supplied fonts);
4. system fonts — Windows / macOS / Linux;
5. recursive search of the above (Linux Noto often lives in nested subdirs).

Do not place commercial fonts here unless their license explicitly permits
redistribution. Noto (SIL OFL) does; `OFL.txt` is kept in this directory for
that case.
