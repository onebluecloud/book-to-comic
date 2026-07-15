# Adaptation Rules

## Series First

Do not compress a whole book into one comic episode. Start from the book structure, then split into episodes, then scenes, then panels. `episode_id: "WHOLE-BOOK"` is invalid for formal output.

## Narrative Spine First

Build `narrative_spine` before listing points: protagonist, opening struggle, and this episode's change. Every concept must attach to a beat in the protagonist's action line. Do not create one independent panel per concept.

Before `narrative_spine`, build `adaptation_strategy`: `soul_conflict`, `chosen_form`, `why_fits`, `avoided_cliches`, and `novelty_hook`. The strategy must be tailored to this book: if it can be moved to a very different book unchanged, it is too generic. List at least three cliches to avoid.

`narrative_spine` must include `foil` and a concrete `spine_event` with `what`, `stakes`, and `trigger`. The event is the pressure line that keeps scenes from becoming detached point demonstrations.

## Evidence Story IR

Every formal episode includes `story_ir`, the evidence-driven bridge from book material to drawable comics:

- `source_chunks`: chapter ID, paragraph range, and short excerpt. Keep chunks small enough to audit and stable enough to cite.
- `scene_beats`: one beat per story movement with `goal`, `obstacle`, `turn`, `visual_hook`, and `source_refs`.
- `panel_scripts`: one script per panel with `beat_id`, `panel_role`, `action_verb`, and `source_refs`.

Do not let evidence stop at episode-level `source_refs`. Each panel also carries `source_refs` to the source chunks that justify its action, motivation, or invented compression. If a key moment has no source support, mark it as creative adaptation in QA or rewrite it.

## Episode Scope

Each episode needs one `primary_thesis`. It can include at most two support mechanisms. If an episode needs more, split it.

## Dynamic Panel Count

- 4-6 panels: short hook or simple idea.
- 6-10 panels: standard mobile episode.
- 10-14 panels: scene-heavy literature or novels.
- 16 panels: hard cap only.

## Fiction

Adapt by chapter, scene, plot beat, or character arc. Preserve causality and emotional stakes. Do not flatten a novel into a few explanatory cards.

## Nonfiction

Adapt by thesis, mechanism, example, counterexample, and behavior change. Use concrete life scenes to make the idea visible: bedroom, subway, workstation, dining table, phone screen, street, family conversation, group chat. The discourse scene can connect or punctuate, but it cannot become the main visual world.

## Scene Layer

Each episode uses at least three `scenes[]`. Each scene is one continuous event with a location, action, emotional change, and `panels[]`. `environment_bible.json` marks each environment as `life_scene`, `discourse`, or `metaphor`; at least half of the scenes must be `life_scene`, and a single location cannot dominate more than half the episode.

Scenes must escalate rather than sit side-by-side. Each scene needs `escalation_role`: `setup`, `complication`, `crisis`, or `turn-and-action`; the first scene sets up the pressure, the last scene must be `turn-and-action`. Each scene needs `callback_to_spine_event`. The final or turn scene must include `change_shown_by_action`, a visible action by the protagonist that shows change instead of merely stating the lesson.

## Shot Continuity

Each scene uses at least three shot sizes from `establishing`, `wide`, `medium`, `close-up`, `insert`, `over-shoulder`, and `insert/over-shoulder`. Except on the first panel of each scene, every panel needs `continuity_from_prev`: `same-scene-push-in`, `next-action-beat`, `reaction-shot`, `cause-effect`, `match-cut`, or `scene-transition`.

## Drawable Panel Contract

Each panel must be drawable before image generation:

- `panel_role`: one of `establishing`, `action`, `reaction`, `turn`, `insert`, `transition`, `payoff`.
- `action_verb`: a visible verb such as opens, drops, reaches, looks away, writes, waits, tears, hesitates. Avoid pure mental labels like "realizes" unless the visual action also shows it.
- `reading_order`: unique positive integer across the episode.
- `balloon_budget`: `max_chars` and `actual_chars`; text over budget must be compressed before art generation.

This is a storyboard rule, not lettering decoration. If a panel has no job, no action verb, or an overflowing balloon, it is not ready for final art.

## Overlay Copy

Use at most three short sentences per panel for carousel cards:

1. role line when useful;
2. plain-language explanation;
3. reality mapping.

The final panel of a continuing episode uses: theme closure, spoiler-free hook, comment prompt.

## Continuity

Record character appearance, wardrobe, props, environment anchors, and transitions. Each panel includes only actually present characters. Before final composition, run the story gate: deterministic `validate-story`, Chinese lettering proofread, source coverage review, adjacent-panel shuffle test, drawable panel review, and scene diversity review.

The LLM gate also runs story-arc checks: scene reorder must break the story, removing a middle scene must break the event chain, and the ending must show change through action. It also checks novelty: the selected form must not be a reusable template or a repeat of recent form fingerprints.

Deterministic QA metrics include Source Coverage, Drawable Panel Rate, Balloon Overflow Rate, and reading order pass/fail.
