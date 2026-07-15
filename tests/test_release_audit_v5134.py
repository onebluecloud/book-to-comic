"""v5.13.4 taste-contract regressions (field report, not an external audit).

Field report 2026-07-13: a real mass_traffic run of 桃花源记 landed on the
monochrome ink-sketch lane and default white cards — both taste-critical
choices were advisory, so a third-party user's agent could (and did) drift.
These tests pin the new deterministic contract:

- choose_style_for_brief demotes low-reach lanes for mass_traffic;
- validate-story blocks mass_traffic + low-reach style unless the USER's
  explicit choice is recorded (custom_art_style);
- formal compose requires an explicit card_theme (three values, no silent
  default); set-card-theme records it; add-episode carries it across a series.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from book_to_comic.art_style import set_card_theme, set_custom_art_style
from book_to_comic.artifact_materializer import init_project, required_card_theme
from book_to_comic.composer import CARD_THEMES
from book_to_comic.series import add_episode_project, init_series
from book_to_comic.story_gate import StoryGateError, validate_story_gate
from book_to_comic.styles import choose_style_for_brief, low_reach_style_ids


def _ink_leaning_brief() -> dict[str, int]:
    """Axes that read as 古典文学: the lane straddle from the field report."""
    return {
        "emotion": 5,
        "plot": 3,
        "abstract_ideas": 4,
        "humor": 0,
        "mobile": 2,
        "historical_world": 4,
        "text_density": 5,
        "premium_editorial": 5,
        "action": 0,
        "warmth": 2,
    }


def _story_gate_issue_codes(root: Path) -> set[str]:
    # The gate writes qa/story-gate-report.json before raising — read the
    # written report so the helper does not depend on the exception payload.
    try:
        validate_story_gate(root, require_llm_gate=False)
    except StoryGateError:
        pass
    report = json.loads((root / "qa" / "story-gate-report.json").read_text(encoding="utf-8"))
    return {issue.get("code", "") for issue in report["deterministic_gate"]["issues"]}


def _set_project_field(root: Path, key: str, value: str) -> None:
    project_file = root / "project.json"
    data = json.loads(project_file.read_text(encoding="utf-8"))
    data[key] = value
    project_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _set_episode_style(root: Path, style_id: str) -> None:
    episode_file = root / "story" / "episode-001.json"
    data = json.loads(episode_file.read_text(encoding="utf-8"))
    data["style_id"] = style_id
    episode_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class StyleSelectorIntentTests(unittest.TestCase):
    def test_low_reach_set_is_derived_from_market_table(self) -> None:
        # General rule, data-derived: only styles ranked tier B everywhere in
        # market_style_preferences.json count as low-reach. The mass color
        # lanes must never appear in the set.
        avoid = low_reach_style_ids()
        self.assertIn("ink-sketch", avoid)
        for mass_lane in ("manhua", "webtoon-manhwa", "manga"):
            self.assertNotIn(mass_lane, avoid)

    def test_mass_traffic_never_returns_low_reach_lane(self) -> None:
        result = choose_style_for_brief(_ink_leaning_brief(), delivery_intent="mass_traffic")
        self.assertNotIn(result.style_id, low_reach_style_ids())

    def test_demotion_is_structural_for_any_brief(self) -> None:
        # The floor demotion must hold across arbitrary axis mixes, not just
        # the calibrated field-report brief.
        for emotion in (0, 3, 5):
            for premium in (0, 3, 5):
                brief = dict(_ink_leaning_brief(), emotion=emotion, premium_editorial=premium)
                result = choose_style_for_brief(brief, delivery_intent="mass_traffic")
                self.assertNotIn(result.style_id, low_reach_style_ids())

    def test_showcase_intent_keeps_literary_lane_available(self) -> None:
        natural = choose_style_for_brief(_ink_leaning_brief())
        if natural.style_id not in low_reach_style_ids():
            self.skipTest(f"matrix no longer favors a low-reach lane for this brief ({natural.style_id})")
        # Same brief: no intent (or showcase) may pick ink-sketch; mass_traffic
        # must move off it and say why.
        showcase = choose_style_for_brief(_ink_leaning_brief(), delivery_intent="hardcore_showcase")
        self.assertEqual(showcase.style_id, natural.style_id)
        mass = choose_style_for_brief(_ink_leaning_brief(), delivery_intent="mass_traffic")
        self.assertNotIn(mass.style_id, low_reach_style_ids())
        self.assertIn("mass-traffic-demotion", mass.reason)


class StoryGateStyleIntentTests(unittest.TestCase):
    def _project(self, tmp: str, *, delivery_intent: str) -> Path:
        root = Path(tmp) / "proj"
        init_project("测试书", root, delivery_intent=delivery_intent)
        return root

    def test_mass_traffic_low_reach_style_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp, delivery_intent="mass_traffic")
            _set_episode_style(root, "ink-sketch")
            self.assertIn("style-mass-traffic", _story_gate_issue_codes(root))

    def test_user_recorded_style_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp, delivery_intent="mass_traffic")
            _set_episode_style(root, "ink-sketch")
            set_custom_art_style(root, "黑白钢笔文学墨线，用户点名要的排线质感")
            self.assertNotIn("style-mass-traffic", _story_gate_issue_codes(root))

    def test_showcase_intent_not_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp, delivery_intent="hardcore_showcase")
            _set_episode_style(root, "ink-sketch")
            self.assertNotIn("style-mass-traffic", _story_gate_issue_codes(root))

    def test_mass_traffic_color_lane_not_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp, delivery_intent="mass_traffic")
            _set_episode_style(root, "manhua")
            self.assertNotIn("style-mass-traffic", _story_gate_issue_codes(root))


class CardThemeContractTests(unittest.TestCase):
    def test_missing_theme_refused_with_fix_instruction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj"
            init_project("测试书", root)
            with self.assertRaises(ValueError) as ctx:
                required_card_theme(root)
            self.assertIn("set-card-theme", str(ctx.exception))

    def test_invalid_theme_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj"
            init_project("测试书", root)
            _set_project_field(root, "card_theme", "neon")
            with self.assertRaises(ValueError):
                required_card_theme(root)

    def test_each_legal_theme_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj"
            init_project("测试书", root)
            for theme in CARD_THEMES:
                set_card_theme(root, theme)
                self.assertEqual(required_card_theme(root), theme)

    def test_setter_rejects_unknown_theme_and_missing_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "proj"
            init_project("测试书", root)
            with self.assertRaises(ValueError):
                set_card_theme(root, "vaporwave")
            with self.assertRaises(FileNotFoundError):
                set_card_theme(Path(tmp) / "nowhere", "gallery")


class SeriesCardThemeCarryTests(unittest.TestCase):
    def test_add_episode_inherits_previous_theme(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            series = Path(tmp) / "series"
            series.mkdir()
            init_series(series, book="测试书", episodes=[{"episode_id": "EP01", "title": "一"}, {"episode_id": "EP02", "title": "二"}])
            first = add_episode_project(series, episode_id="EP01")
            set_card_theme(first["project_dir"], "gallery")
            second = add_episode_project(series, episode_id="EP02")
            self.assertEqual(second["card_theme"], "gallery")
            data = json.loads((Path(second["project_dir"]) / "project.json").read_text(encoding="utf-8"))
            self.assertEqual(data.get("card_theme"), "gallery")


if __name__ == "__main__":
    unittest.main()
