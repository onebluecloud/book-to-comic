from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Suitability:
    is_applicable: bool
    category: str
    reason: str


@dataclass(frozen=True)
class CoreIdea:
    title: str
    kernel: str
    dramatization: str


@dataclass(frozen=True)
class Character:
    name: str
    concept: str
    visual: str
    personality: str
    prompt_fragment: str


@dataclass(frozen=True)
class Panel:
    index: int
    beat: str
    visual: str
    dialogue: tuple[str, ...]
    narration: str
    comment_hook: str = ""
    scene_setting: str = ""
    interior_monologue: str = ""
    connective_prose: str = ""
    reality_mapping: str = ""
    card_copy: tuple[str, ...] = ()
    # Snapshot of text_variants.long_form taken while the raw mapping is still
    # available. Renderers receive this frozen dataclass (not the mapping), so
    # without the snapshot they can never see text_variants and fall back to
    # concatenating internal production fields (scene_setting/connective_prose/
    # reality_mapping) into reader-facing captions.
    long_copy: tuple[str, ...] = ()
    invented_dialogue: tuple[str, ...] = ()
    visual_weight: str = "normal"
    layout_hint: str = "normal"
    beat_duration: str = "normal"
    visual_density: str = "medium"
    text_density: str = "medium"
    reveal_priority: str = "normal"
    pause_after: bool = False
    emotional_anchor: bool = False
    anchor_subject: str = ""
    anchor_note: str = ""
    hook_type: str = ""
    hook_line: str = ""
    is_cover_source: bool = False


@dataclass(frozen=True)
class TextBlock:
    block_id: str
    purpose: str
    text: str
    source_refs: tuple[str, ...] = ()
    max_chars: int = 0


@dataclass(frozen=True)
class TextVariant:
    variant_id: str
    purpose: str
    blocks: tuple[TextBlock, ...]


@dataclass(frozen=True)
class LetteringBlock:
    block_id: str
    text: str
    anchor: str
    priority: int = 1
    max_chars: int = 0


@dataclass(frozen=True)
class ComicPanel:
    panel_id: str
    reading_order: int
    scene_id: str
    panel_role: str
    story_function: str
    source_refs: tuple[str, ...]
    argument_ids: tuple[str, ...] = ()
    text_variants: tuple[TextVariant, ...] = ()
    lettering_blocks: tuple[LetteringBlock, ...] = ()
    emotional_anchor: bool = False
    anchor_subject: str = ""
    anchor_note: str = ""
    hook_type: str = ""
    hook_line: str = ""
    is_cover_source: bool = False


@dataclass(frozen=True)
class StyleSpec:
    id: str
    name: str
    reference: str
    suitable_for: str
    prompt_spec: str
    schema_version: str = "1.0"
    short_name: str = ""
    taxonomy: dict[str, Any] = field(default_factory=dict)
    selection: dict[str, Any] = field(default_factory=dict)
    art_direction: dict[str, Any] = field(default_factory=dict)
    prompt_blocks: dict[str, tuple[str, ...]] = field(default_factory=dict)
    qa: dict[str, tuple[str, ...]] = field(default_factory=dict)
    substyles: tuple[dict[str, Any], ...] = ()
    sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class ArtBrief:
    book_type: str
    time_period: str
    geography: str
    narrative_density: int
    emotional_intensity: int
    action_intensity: int
    abstractness: int
    humor: int
    world_complexity: int
    target_platform: str
    audience: str
    text_density: int


@dataclass(frozen=True)
class StyleSelectionResult:
    style_id: str
    variant_id: str
    score: float
    reason: str


@dataclass(frozen=True)
class PanelArtSpec:
    panel_id: str
    characters_present: tuple[str, ...]
    environment_id: str
    time: str
    shot_size: str
    camera_angle: str
    lens_feel: str
    focal_point: str
    foreground: str
    midground: str
    background: str
    action: str
    emotion: str
    eyeline: str
    props_and_states: dict[str, str]
    continuity_from: str
    transition_to_next: str
    lettering_safe_zone: str
    aspect_ratio: str


@dataclass(frozen=True)
class AdaptationPackage:
    book_title: str
    author: str
    episode_title: str
    suitability: Suitability
    covered_points: tuple[str, ...]
    core_ideas: tuple[CoreIdea, ...]
    methods: tuple[str, ...]
    light_shell: str
    hard_core: str
    characters: tuple[Character, ...]
    character_relationship: str
    storyboard: tuple[Panel, ...]
    title_candidates: tuple[str, ...]
    style_id: str
