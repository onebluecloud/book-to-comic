# Quality Polish And Copywriting Gates

Use this reference for every formal v4 project before composition. It is the source for `qa/appeal-report.json`, not an optional polish note. Also reread it when the user asks for higher finish, stronger copy, more premium visual quality, better hooks, better emotional impact, or when an episode feels correct but not yet compelling.

Do not copy external examples into outputs. Convert the principles below into project-specific art direction, panel prompts, lettering text, and QA notes.

## Selection Principle

Only adopt improvements that can be checked in a comic production flow:

- a stronger visual focus;
- a more memorable character;
- clearer light, material, and spatial logic;
- a more scannable and emotionally directed caption;
- a measurable review or A/B hypothesis.

Reject vague advice such as "make it prettier", "more cinematic", or "more emotional" unless it is translated into a drawable or editable requirement.

## Visual Polish Gates

### 3-Second Focus

For each panel and final card, shrink it to phone thumbnail size and ask:

- Can the main character, main action, and key prop be identified in 3 seconds?
- Is there only one primary focal point?
- Does the caption area compete with the art?

If not, simplify background contrast, crop closer, reduce secondary details, or move the lettering.

### Thumbnail Pass

Before formal generation, each important scene needs a composition decision:

- define 3-6 possible framing options mentally or in notes;
- choose one camera reason: reveal setting, increase pressure, show relation, show decision, or create aftertaste;
- record `focal_point`, `foreground`, `midground`, `background`, `action_vector`, and `negative_space`.

For high-stakes panels such as opening hook, turning point, climax, and final hook, prefer 6-12 thumbnails when time allows. Do not start from a full-detail prompt before the focal structure is chosen.

### Character Appeal

Character appeal is not prettiness. Lock:

- one primary appeal axis: cold, warm, tired, elegant, wild, innocent, severe, wounded, comic, etc.;
- two visual memory features: hair mass, eye shape, posture, hero garment, prop, color accent, scar, glasses, bag, silhouette;
- at least one body-language habit: looking down before answering, gripping a strap, leaning away, smoothing paper, etc.

QA:

- silhouette test: if filled black, can the character still be recognized by posture, hair mass, or costume?
- face test: if hair and costume are hidden, can major recurring characters still be separated?
- expression test: the episode must include more than neutral talking faces; include at least one suppressed, conflicted, or transitional expression.

### Light And Material Logic

Every scene must define a motivated light source and material cues:

- main light direction;
- ambient light color;
- whether rim light exists and why;
- material words for major surfaces: matte, worn, translucent, polished, soft, rough, heavy, thin, old, damp.

Do not add glow, bloom, or rim light just because it looks premium. If effect layers were removed, the figure and key action should still read.

Material QA:

- skin / hair / cloth / metal / wood / paper should not use the same highlight and edge logic;
- key props need use history or function logic when relevant: folded corner, worn handle, scratched edge, creased paper, marked cup rim;
- background details should support story, not compete with faces, hands, or key props.

### Emotion Anchor Shot

Each episode should contain at least one "emotion anchor shot": a panel that the reader can remember after scrolling away.

Good anchors are not generic big close-ups. They combine:

- a concrete action;
- a body reaction;
- a key prop or environment detail;
- a caption that lands the emotional turn.

Examples of anchor types:

- hand hovering over the reply box;
- blank invitation card being folded into a pocket;
- lamp light cutting across an unread page;
- chair left empty beside an open door.

## Copywriting Gates

### Copy Job

Before writing final captions, decide the job of each line:

- hook: make the reader stop;
- context: explain who, where, and what is happening;
- translation: turn the book's concept into plain life language;
- emotion: make the reader feel the pressure or release;
- memory: leave a sentence worth repeating;
- action: invite comment, next episode, or continued reading.

One caption cannot do every job. Put the most important job first.

### Tone Matrix

Pick a stable voice for the series or episode, then adjust tone per panel:

| Tone | Use For | Risk |
|---|---|---|
| restrained trailer | covers, hooks, endings, classic literature | can sound pretentious if too abstract |
| poetic but concrete | literary panels and emotional pauses | can become empty if it lacks objects/actions |
| character interior | first-person conflict and turning points | can become melodramatic |
| documentary concrete | production notes, nonfiction explanation, source-heavy panels | can feel flat if no emotion |
| conversion concise | title, subtitle, CTA, comment hook | can become cheap if it exaggerates |

Never use shock-copy, fake urgency, cheap internet slang, or self-help slogans to make a classic or serious book "relatable".

### Length Match

Use the shortest form that still preserves depth:

- microcopy: fewer than 3 short sentences; buttons, hooks, final comment question;
- short comic caption: 1-3 sentences; most panels;
- medium note: 2-3 short paragraphs; review notes or production explanation;
- long note: 3+ paragraphs only for manuals, release notes, or book-level explanations.

In comic cards, keep the existing rule: at most three short lines. If the thought is complex, split it across panels or turn part of it into a visual action.

### Sentence Polish

Before composing:

- Replace abstract adjectives with visible evidence: not "她很焦虑", but "她把筷子攥得很紧".
- Use strong verbs where appropriate: press, fold, avoid, push back, open, stop, tear, hold, look away.
- Avoid repeated "很/非常/极其" and generic praise.
- Use rhythm: a longer context line may be followed by a short landing line.
- Make every panel contain at least one concrete noun or action.
- If a sentence cannot be visualized, rewrite it.

### Memory Sentence

Each episode should have one memory sentence, usually in the final third. It must be:

- accurate to the book;
- short enough to quote;
- tied to a visual action;
- not generic enough to fit any book.

Weak: `你要勇敢做自己。`

Better pattern: `她不是要赢过谁。她只是第一次不把关系当考场。`

### Scannability

For cards, readers should understand the arc by scanning only titles plus gold/primary lines.

Check:

- first card tells who and what trouble;
- middle cards escalate through visible actions;
- final card gives closure plus next-episode curiosity;
- each card title is precise, not earthy clickbait and not abstract literary fog.

## A/B And Feedback Loop

When preparing covers, hooks, subtitles, or final comment prompts, create at least two versions if time allows:

- A: clear/direct;
- B: more image-based or more emotionally specific.

Record the hypothesis, not just which one "feels better":

| Field | Example |
|---|---|
| object | cover title / first card hook / final comment question |
| A | `关系不是排行榜` |
| B | `别人的人生，不是你的成绩单` |
| hypothesis | B may create stronger self-recognition; A is more concept-clean |
| metric | stop rate, completion rate, save rate, comment quality |

Good feedback questions:

- What did you see first?
- What sentence did you remember?
- Where did you want to swipe away?
- Did the ending make you want the next episode?

Do not ask only "which one do you like?"

## Final Polish Checklist

Before delivery, record the first five items in `qa/appeal-report.json` as required checks with non-empty evidence. Record the rest in `review/qa-report.json` when relevant:

- `three_second_focus`: pass / warn / fail with phone-thumbnail evidence;
- `emotion_anchor`: panel id and why it works;
- `character_appeal`: one memory feature per recurring character;
- `memory_sentence`: selected final line;
- `scan_test`: whether card titles and primary lines alone explain the arc;
- `light_material_logic`: motivated light and key materials;
- `copy_job`: hook/context/translation/emotion/memory/action coverage;
- `lighting_variation`: at least two meaningful light directions or temperatures;
- `composition_density_curve`: sparse/dense rhythm is visible, not flat medium-density cards;
- `palette_shift`: scene changes have visible color movement when appropriate;
- `ab_candidates`: if cover/hook/comment alternatives were produced.
