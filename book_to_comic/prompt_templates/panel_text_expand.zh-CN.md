Task: expand one comic panel into production-ready zh-CN lettering.

Use the project narrative identity lock, the source refs, and the panel action. Return strict JSON only.

Required output keys:
- panel_id
- text_layers.dialogue
- text_layers.scene_setting
- text_layers.interior_monologue
- text_layers.connective_prose
- text_layers.narration
- text_layers.reality_mapping
- text_layers.comment_hook
- text_variants.long_form
- text_variants.card_form
- invented_dialogue
- text_notes

Rules:
- `long_form` may carry richer scene setting, psychology, cause-effect bridge, and plain-language translation.
- `card_form` is mobile copy: max 3 paragraphs, short, scannable, not article-like.
- Do not use forbidden generic or cross-book phrases.
- Ground the life bridge in this book; do not force a trendy analogy.
