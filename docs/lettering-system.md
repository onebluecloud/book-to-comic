# Comic Lettering System

Updated: 2026-06-20

## Goal

The final comic must read as one designed object, not as illustrations with labels pasted on top.

Lettering must satisfy four gates:

1. The raw generated panel art stays clean: no AI-rendered Chinese, pseudo-text, blank signboards, or reserved white boxes inside the art.
2. Post-production lettering must be readable at mobile width.
3. Lettering must not cover faces, hands, key props, or the main action unless a human explicitly approves that panel.
4. Typography, padding, line height, borders, and caption style must follow the selected comic style.

## Lettering modes (`lettering_mode`)

Set `lettering_mode` in `project.json` to pick where text lives. `init-project` writes `hybrid` as the project default (dialogue balloons + narration captions); a project.json that omits the field falls back to the `balloon` constant, and compose additionally auto-switches balloon→hybrid for painterly flat styles.

| mode | in-image balloons | in-image SFX | dialogue in caption | use for |
|---|---|---|---|---|
| `balloon` | yes | yes | removed (shown in balloon) | print / CBZ / long-scroll reading, full comic feel |
| `hybrid` | no | yes | yes | mobile carousels — SFX stay on the art, dialogue sinks to the caption so small text stays readable and balloons never cover faces |
| `caption-only` | no | no | yes | maximum art visibility; artwork is never overpainted |

Rules:

- SFX (拟声词) belong to the artwork, so `balloon` and `hybrid` both keep them in-image; only `caption-only` moves everything out.
- Any dialogue a mode does not draw in-image must survive in the caption. `caption_lines_for_mode` appends a balloon line if the caption is missing it, so speech is never silently lost.
- The mode is read once in `compose_artifact_project` and threaded to every composer surface (long image, cards, comic pages), so one setting keeps all deliverables consistent.

## Research Takeaways

Practical lettering guidance from comics lettering resources points to the same rules:

- Lay out text first, then draw the balloon or caption container around it.
- Keep normal dialogue size consistent; only vary it for a deliberate effect such as shouting or whispering.
- Keep inner padding and negative space consistent so text does not feel cramped or isolated.
- Balloons should ideally avoid figures; when overlap is unavoidable, never cover important faces or hands.
- Balloon tails should point toward the speaker's mouth area and should not cross.
- Webtoon/mobile output needs larger, cleaner type and more vertical breathing room than print.

Useful references:

- Blambot, "Comic Book Grammar & Tradition": https://blambot.com/pages/comic-book-grammar-tradition
- Blambot, "Better Letterer": https://blambot.com/pages/lettering-tips
- Todd Klein, "Balloon Placement": https://kleinletters.com/BalloonPlacement.html
- Clip Studio Tips, "Letter Your Webtoon Like a Pro": https://tips.clip-studio.com/en-us/articles/3751

## Layer Model

The workflow has three layers:

1. **Raw art layer**: approved panel images in `assets/panels/01.png` through `assets/panels/NN.png`. These are never modified with text.
2. **Lettering plan layer**: a deterministic layout plan chooses panel frame, art rectangle, caption rectangle, font sizes, padding, and line spacing before drawing.
3. **Final raster layer**: the composer renders the final long image, subtitled panels, contact sheets, and review package from the plan.

This prevents the common failure where a late speech bubble is dropped on top of a face because no safe text area was planned.

## Placement Policy

The `hybrid` default policy is **balloons for dialogue, captions for narration**:

- Character dialogue goes into in-art balloons planned by the host in `story/balloon_plan.json`. The host IS the subject detector: it looks at each approved panel and hands the renderer normalized safe-zone boxes plus mouth anchors. `validate-balloon-plan` deterministically checks bounds, quoted-dialogue fidelity, and reading order; the renderer (`balloons.py`) draws speech/thought/shout/whisper/narration-box shapes with tails, kinsoku line breaking, and speaker-prefix stripping.
- Narration, connective prose, reality mapping, prices, equations, and comment hooks stay outside the raw art in a style-matched caption area. Lines that entered a balloon are automatically removed from the caption.
- A project without a balloon plan still composes caption-only (backward compatible), but a formal comic delivery is expected to carry one — captions alone read as illustration-with-labels, not comics.

Either way, "comic text" means well-designed post-production lettering, not AI text inside the art.

## Style Presets

### editorial

Use for New Yorker / literary editorial scenes such as `《浮士德》`.

- Container: open caption integrated into the same paper panel as the art; no filled subtitle band.
- Font: Chinese serif body text, regular weight; title and small panel labels may use a restrained bold face.
- Color: charcoal text, low-contrast beige border, no pure white blocks.
- Shape: no bubble and no separate filled text box; use a thin quiet rule only when separation is needed.
- Spacing: generous art-to-caption gap; line height around 1.35-1.45.
- Rule: do not cover the image. The caption should feel like New Yorker-style editorial captioning: quiet, literate, and visually part of the illustration.

### ink-sketch

- Container: minimal off-white caption band or thin rule below image.
- Font: regular weight, slightly smaller than editorial, more air.
- Color: black/gray only.
- Rule: avoid round glossy bubbles; keep it literary.

### franco-belgian-bd

- Container: clean caption strip below art, with optional small rounded dialogue balloon only when a safe zone exists.
- Font: clear medium-weight sans-serif.
- Border: precise ink line, modest radius.
- Rule: no heavy shadows; clarity and tidy geometry matter more than decoration.

### comic-strip

- Container: classic simple caption strip or small balloon.
- Font: friendly bold sans-serif.
- Rule: short text only; split long narration across panels.

### manga

- Container: high-contrast caption strip outside art for Chinese text.
- Font: bold but not oversized; stronger contrast than editorial.
- Rule: no fake manga SFX generated by the image model.

### webtoon-manhwa

- Container: vertical-scroll text blocks between art beats.
- Font: larger body size, clean line height, high mobile readability.
- Rule: use more vertical whitespace than print-like styles.

### manhua

- Container: clean white or soft-tinted caption strips with modern spacing.
- Font: Chinese sans-serif with medium weight.
- Rule: avoid crowding; mobile readability wins.

### doodle

- Container: notebook-like note strip, softer border, slightly looser spacing.
- Font: regular or rounded sans-serif; avoid corporate heaviness.
- Rule: should feel hand-made, not like a PowerPoint label.

### retro-halftone

- Container: cream or pale yellow caption box with stronger ink border.
- Font: bold condensed feeling if available; otherwise bold sans-serif.
- Rule: strong contrast is acceptable, but keep text outside art unless a safe zone exists.

## Typography Tokens

Use width-relative sizing with clamps:

- Title: `clamp(36, width * 0.036, 56)`
- Subtitle: `clamp(20, width * 0.018, 28)`
- Panel label: `clamp(24, width * 0.026, 36)`
- Body: `clamp(36, width * 0.034, 50)` for most styles; editorial subtracts from this base so long literary captions stay calmer.
- Caption padding x: `width * 0.028`
- Caption padding y: `body_size * 0.70`
- Body line gap: `body_size * 0.32`
- Paragraph gap: `body_size * 0.28`

For literary/editorial output, keep the body calmer than retro/comic-strip styles, but never reduce it to footnote size. At 1440 px width, editorial body text should sit around 38-42 px so long literary captions do not look shouty or over-spaced.

## Chinese Punctuation Rules

Before rendering Chinese overlay text:

1. Apply basic kinsoku-style line breaking: do not start a line with `，。！？；：、）」》` and do not end a line with `（「《`.
2. Prefer corner quotes `「」` for quoted Chinese phrases in final captions. Curly quotes `“”` can create awkward side spacing in Song-style fonts.
3. Keep punctuation attached to the word or phrase it belongs to; do not insert manual spaces around Chinese punctuation.
4. If a line looks over-spaced, reduce editorial body size before adding letter spacing. Do not use artificial character spacing for Chinese captions.

## Text Editing Gate

Before rendering:

1. Remove duplicate text between dialogue bubbles and captions.
2. Split long text into two short paragraphs if it exceeds about 45 Chinese characters.
3. If a panel has no actual speaker dialogue, do not invent a speech bubble just to make it "more comic".
4. The comment hook belongs in the final panel's caption area unless the visual design reserves a separate ending card.

## Copy Tone And Memory Gate

Before final composition, decide the job of each caption line:

- hook: make the reader stop;
- context: explain who, where, and what is happening;
- translation: convert the book's concept into plain life language;
- emotion: make the reader feel the pressure, loss, irony, or release;
- memory: leave one quotable sentence;
- action: invite a comment or the next episode.

Choose a tone before editing the sentence:

- restrained trailer: hooks, endings, classic literature, philosophical nonfiction;
- poetic but concrete: literary pauses and emotional aftertaste;
- character interior: first-person struggle and turning points;
- documentary concrete: source-heavy nonfiction or process notes;
- conversion concise: cover titles, subtitles, CTA, comment hooks.

Hard rules:

- Do not use shock-copy, cheap internet slang, fake urgency, or self-help slogans to make serious books "relatable".
- Replace abstract adjectives with visible evidence. Prefer `她把筷子攥得很紧` over `她很焦虑`.
- Each episode needs one memory sentence that is accurate to the book, short enough to repeat, and tied to a visible action.
- Card titles plus primary/gold lines should pass a scan test: a reader skimming only those lines can understand who is in trouble, what changed, and why the next episode matters.

## Mobile Carousel Cards

For mobile carousel reading, export one panel per PNG at `1080 x 1440`.

- Layout: dark top and bottom bands with the panel art centered between them. The art is never cropped just to fill the frame.
- Copy: at most three short overlay sentences per card, following **role line / plain-language explanation / reality mapping**. The final card may use the comment hook as the third sentence.
- Typography: use the same style family as the episode. Editorial cards use Chinese serif type, charcoal or warm paper text on a deep brown-black ground, and restrained warm-gold accents.
- Spacing: leave enough top and bottom breathing room for mobile reading; do not paste a white subtitle strip under the image.
- Fit rule: if the copy wraps too much, edit the sentence shorter before reducing type below mobile-readable size.

## Composition Flow

1. Validate raw panels.
2. Resolve the lettering preset from `package.style_id`.
3. Build a page layout plan before drawing.
4. Verify each panel has `caption_rect.y0 > art_rect.y1`.
5. Render the page.
6. Render a contact sheet and review package.
7. Do a visual check before delivery.

## Faust EP1 Decision

For `《浮士德》EP1` the locked style is `editorial`, so the correct text treatment is:

- no in-art speech bubbles;
- no stark white boxes;
- open caption on the same warm paper surface, with no filled subtitle band;
- Chinese serif body type;
- calm literary typography;
- enough image scale that the art remains the hero;
- no text covering Faust, Mephisto, the chair, or the red thread.
