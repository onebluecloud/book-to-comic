"""v5.13.5 convergence-signal regressions (field report, not an external audit).

Field report 2026-07-13: a real v5.13.4 run produced a passing, correct
color deliverable, then the host agent kept going — re-planning EP01 and
preparing to re-render all panels for a "better" second version, roughly
doubling the run before stalling. Nothing in the pipeline told the agent that
a clean delivery-gate pass is the END of the episode's work.

These tests pin the machine-readable completion marker so every surface
(delivery stamp, compose return, CLI banner) can announce a clean stop.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from book_to_comic.artifact_materializer import init_project
from book_to_comic.delivery_gate import (
    COMPLETION_GUIDANCE,
    COMPLETION_STATE_DELIVERED,
    COMPLETION_STATE_FORCED,
    load_delivery_stamp,
    stamp_delivery,
)


def _project(tmp: str) -> Path:
    root = Path(tmp) / "proj"
    init_project("测试书", root)
    return root


class DeliveryCompletionMarkerTests(unittest.TestCase):
    def test_clean_pass_marks_delivered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            stamp = stamp_delivery(root, gates=["validate-story"], panel_count=8, forced=False)
            self.assertEqual(stamp["completion"]["state"], COMPLETION_STATE_DELIVERED)
            self.assertTrue(stamp["completion"]["guidance"].strip())
            # Persisted, not just returned — series-status / other readers see it.
            reloaded = load_delivery_stamp(root)
            self.assertEqual(reloaded["completion"]["state"], COMPLETION_STATE_DELIVERED)

    def test_forced_bypass_is_not_a_clean_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _project(tmp)
            stamp = stamp_delivery(
                root,
                gates=["validate-story"],
                panel_count=8,
                forced=True,
                forced_reason="gates bypassed",
            )
            self.assertEqual(stamp["completion"]["state"], COMPLETION_STATE_FORCED)
            self.assertNotEqual(stamp["completion"]["state"], COMPLETION_STATE_DELIVERED)

    def test_guidance_carries_the_actual_stop_constraints(self) -> None:
        # The whole point is the wording — a blank or watered-down guidance
        # would pass an existence check but not steer the agent. Assert the
        # three load-bearing instructions survive.
        self.assertIn("终态", COMPLETION_GUIDANCE)
        self.assertIn("add-episode", COMPLETION_GUIDANCE)
        for forbidden in ("重规划", "重抽", "重 compose"):
            self.assertIn(forbidden, COMPLETION_GUIDANCE)


if __name__ == "__main__":
    unittest.main()
