# Workflow Reference

Use this when running the full host-native Book-to-Comic production path.

1. Create or extract the project with `init-project` or `extract`. The project must initialize `story/episode-001.json` with `planning_status=needs_host_planning`; it must not generate generic characters, a study room, a guide figure, or root-level panels.
2. If a legacy project exists, run `migrate-legacy-project --project <project>` once. After migration, formal modules must read only `story/episode-001.json`.
3. Build source chunks with `source-chunk` when `source/raw_text.txt` exists. The host then writes series planning, concept units, adaptation strategy, narrative spine, scenes, panels, character bible, environment bible, visual identity, and narrative identity.
4. Validate planning before art: `validate-character-bible`, `validate-environment-bible`, `validate-visual-identity`, `validate-distinctiveness`, `validate-narrative-identity`.
5. Run `build-story-ir`. Treat failures as host-planning gaps. This command must not guess semantic fields; missing source refs, panel roles, or action verbs should be fixed in the episode JSON by the host.
6. Run `validate-source-coverage`, `validate-source-claims`, and `validate-story`. `validate-story` checks causal scene linkage, removable-scene risk, dynamic panel rhythm, shot variety, climax weight, pause density, concept coverage, and deterministic story metrics.
7. Export text prompts with `export-project-text-prompts`. The host writes or repairs `text_layers` and `text_variants.long_form/card_form` from those prompts, preserving semantic anchors.
8. Run text gates: `validate-text-richness` and `validate-text-distinctiveness`. Long form must be specific enough to explain situation, causality, psychology, concept translation, and reality mapping. Card form must be shorter, scan-friendly, and at most three paragraphs.
9. Build visual locks: `build-visual-contract`, then `validate-visual-contract`, then `export-project-prompts` when image prompts need review or host generation.
10. Generate image-only panels through the host-native path: `snapshot-images`, host image generation, optional `recover-session-image`, `materialize-image`, visual QA, and `approve-asset`. Every formal panel image must respect `review/reference-pack.json` panel locks.
11. After all panels are approved, run `validate-project-assets`.
12. Run `validate-lettering-layout` before compose. It blocks overflow, truncation, too many card paragraphs, too-small fonts, and safe-zone collisions.
13. Run `compose-project`. It re-runs asset, visual contract, story, narrative identity, source-claim, text, distinctiveness, and lettering gates before exporting `final/`.
14. If any gate fails, fix only the failing planning, text, asset, or layout item. Do not bypass gates with placeholders, vector drafts, chat previews, or prompt bundles.

The host model performs book understanding, character creation, text writing, source interpretation, and final LLM review. Python performs deterministic extraction, normalization, schema validation, prompt compilation, asset management, QA reports, and layout.
