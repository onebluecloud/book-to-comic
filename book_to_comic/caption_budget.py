"""Single source of truth for caption length budget.

Calibrated 2026-07-09 against 85 panels from six hand-reviewed scripts
(卖炭翁 / 石壕吏 / 木兰诗 / 桃花源记 / 琵琶行 / 孔雀东南飞) — the batch that reads
well by consensus:

    min 12 · p25 35 · median 46 · p75 54 · p90 64 · max 100 · mean 45.4

Both earlier settings were wrong, in opposite directions:

* The B-tier target of 25-40 chars covered only **25%** of those good captions.
  Too tight: it strangles the storyteller cadence into clipped fragments.
* ``empty_narrative_identity``'s 90-160 covered only **1%**. Too loose: it
  actively taught every new project to water-fill and to editorialize — the
  桃花源记 bug, where all 12 panels ended in a free-floating verdict sentence.

Per-panel HARD bounds are floors/ceilings, not quotas. A terse beat may be as
short as 12 chars (observed); anything past 80 is water-filling. The episode
*average* is what steers prose toward the 35-65 body.

Host ``panel_text_policy`` may TIGHTEN these bounds, never loosen them — a host
that writes ``long_form_max_chars: 160`` must not thereby disable the gate.
"""

from __future__ import annotations

# Body target the host writes toward (p25 .. ~p90 of the calibration set).
LONG_FORM_TARGET_MIN = 35
LONG_FORM_TARGET_MAX = 65

# Episode-average floor. Observed mean 45.4; 40 leaves room for terse beats.
LONG_FORM_AVG_MIN = 40

# Per-panel hard bounds.
LONG_FORM_HARD_MIN = 12  # observed min — a legitimately terse beat
LONG_FORM_HARD_MAX = 80  # past p90; beyond this it is padding

# Mobile card copy.
CARD_FORM_TARGET_MAX = 58
CARD_FORM_AVG_MIN = 16
CARD_FORM_HARD_MIN = 8


def clamp_long_max(policy_value: object) -> int:
    """Host policy may lower the per-panel cap, never raise it."""
    if isinstance(policy_value, int) and 0 < policy_value < LONG_FORM_HARD_MAX:
        return policy_value
    return LONG_FORM_HARD_MAX


def clamp_card_max(policy_value: object) -> int:
    if isinstance(policy_value, int) and 0 < policy_value < CARD_FORM_TARGET_MAX:
        return policy_value
    return CARD_FORM_TARGET_MAX
