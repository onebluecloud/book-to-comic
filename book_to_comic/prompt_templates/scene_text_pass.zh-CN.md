Task: run a scene-level text pass for one comic scene.

Return strict JSON only:

```json
{
  "scene_id": "S01",
  "panels": [
    {
      "panel_id": "P01",
      "text_layers": {},
      "text_variants": {},
      "invented_dialogue": [],
      "text_notes": []
    }
  ]
}
```

Rules:
- Keep every panel connected to the previous action.
- `long_form` can be richer; `card_form` is max 3 paragraphs.
- Use the narrative identity; do not reuse another book's voice.
