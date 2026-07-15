"""Regression suite for the 2026-07-12 v5.13.0 release audit (round 2).

Every test reproduces a failure the release audit demonstrated against
v5.13.0; loosening any assertion re-opens a shipped hole.
"""

from __future__ import annotations

import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image

from book_to_comic.artifact_materializer import (
    SCHEMA3_DELIVERY_GATES,
    formal_gate_names,
    init_project,
)
from book_to_comic.delivery_gate import stamp_delivery, validate_delivery
from book_to_comic.grounding_qa import evaluate_export_rights, validate_grounding
from book_to_comic.host_image_batch import prepare_host_image_batch
from book_to_comic.pipeline import check_project, run_pipeline
from book_to_comic.project_layout import load_episode, save_episode, validate_episode_id
from book_to_comic.review_record import REQUIRED_STORY_CHECKS, record_story_review
from book_to_comic.series import add_episode_project, init_series


def _tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="btc-r2-"))


def _noise(width: int, height: int) -> Image.Image:
    rng = random.Random(7)
    image = Image.new("RGB", (width, height))
    image.putdata([(rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(width * height)])
    return image


def _full_profile(root: Path, **overrides) -> None:
    profile = {
        "schema_version": "1.0",
        "book_title": "t",
        "scores": {dim: 1 for dim in ("historical", "textual", "conceptual", "experiential", "procedural", "rights", "cultural")},
        "copyright_status": "public_domain",
        "source_edition": "某社某版",
        "real_person_or_private_source": False,
        "content_safety": {"checked": True, "hard_exclusion_hits": []},
    }
    profile.update(overrides)
    (root / "planning").mkdir(parents=True, exist_ok=True)
    (root / "planning" / "grounding_profile.json").write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")


def _evidence_file(root: Path, *, status: str = "passed", evidence=None) -> Path:
    if evidence is None:
        evidence = [{"source_excerpt": "原文", "final_text": "成稿", "verdict": "一致"}]
    path = root / "review.json"
    path.write_text(
        json.dumps({"checks": [{"name": name, "status": status, "evidence": evidence} for name in REQUIRED_STORY_CHECKS]}, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


class ReviewGateR2Tests(unittest.TestCase):
    """R2-P0-1: failed/unknown checks and junk evidence cannot be approved."""

    def _project(self) -> Path:
        root = _tmp()
        init_project("书", root)
        return root

    def test_all_failed_checks_cannot_be_approved(self):
        root = self._project()
        with self.assertRaises(ValueError):
            record_story_review(
                root, author_pass_id="a", reviewer_pass_id="b", reviewer_kind="human",
                evidence_file=_evidence_file(root, status="failed"),
            )

    def test_unknown_status_blocks(self):
        root = self._project()
        with self.assertRaises(ValueError):
            record_story_review(
                root, author_pass_id="a", reviewer_pass_id="b", reviewer_kind="human",
                evidence_file=_evidence_file(root, status="maybe"),
            )

    def test_verdict_only_evidence_blocks(self):
        root = self._project()
        with self.assertRaises(ValueError):
            record_story_review(
                root, author_pass_id="a", reviewer_pass_id="b", reviewer_kind="human",
                evidence_file=_evidence_file(root, evidence=[{"verdict": "ok"}]),
            )

    def test_hand_written_failed_checks_fail_validate_story(self):
        # Even if the report is hand-edited to approved with failed checks,
        # validate-story re-applies per-check discipline.
        from book_to_comic.review_record import validate_review_checks

        checks = [{"name": name, "status": "failed", "evidence": []} for name in REQUIRED_STORY_CHECKS]
        problems = validate_review_checks(checks, required_names=REQUIRED_STORY_CHECKS, require_pass=True)
        self.assertGreaterEqual(len(problems), len(REQUIRED_STORY_CHECKS))

    def test_appeal_boolean_evidence_rejected(self):
        from book_to_comic.appeal import _has_evidence

        self.assertFalse(_has_evidence(False))
        self.assertFalse(_has_evidence(0))
        self.assertFalse(_has_evidence([]))
        self.assertTrue(_has_evidence("看过第 3 格特写"))


class DeliveryBindingR2Tests(unittest.TestCase):
    """R2-P0-2: stamps bind real outputs and current rights."""

    def _composed_project(self) -> Path:
        root = _tmp()
        init_project("书", root)
        _full_profile(root)
        (root / "final" / "comic.pdf").write_text("pdf", encoding="utf-8")
        stamp_delivery(root, gates=["g"], panel_count=1, public_export_allowed=True)
        return root

    def test_fresh_project_is_neutral(self):
        root = _tmp()
        init_project("书", root)
        self.assertTrue(validate_delivery(root, raise_on_fail=False, write_report=False)["passed"])

    def test_tampered_final_fails(self):
        root = self._composed_project()
        (root / "final" / "comic.pdf").write_text("TAMPERED", encoding="utf-8")
        report = validate_delivery(root, raise_on_fail=False, write_report=False)
        self.assertFalse(report["passed"])
        self.assertTrue(any("modified" in issue for issue in report["issues"]))

    def test_deleted_final_fails(self):
        root = self._composed_project()
        (root / "final" / "comic.pdf").unlink()
        report = validate_delivery(root, raise_on_fail=False, write_report=False)
        self.assertFalse(report["passed"])
        self.assertTrue(any("missing" in issue for issue in report["issues"]))

    def test_stray_file_fails(self):
        root = self._composed_project()
        (root / "final" / "smuggled.png").write_text("x", encoding="utf-8")
        report = validate_delivery(root, raise_on_fail=False, write_report=False)
        self.assertFalse(report["passed"])
        self.assertTrue(any("unexpected" in issue for issue in report["issues"]))

    def test_rights_change_revokes_public_bundle(self):
        root = self._composed_project()
        (root / "final" / "production.zip").write_text("zip", encoding="utf-8")
        _full_profile(root, copyright_status="in_copyright")
        report = validate_delivery(root, raise_on_fail=False, write_report=False)
        self.assertFalse(report["passed"])
        # v5.13.1 audit P0-3: revoked archives are quarantined OUTSIDE final/
        # so a later public compose can never sweep them back into a bundle.
        self.assertFalse(list((root / "final").glob("*REVOKED*")))
        self.assertTrue(list((root / "quarantine" / "revoked-bundles").glob("production.zip.*REVOKED")))

    def test_story_change_after_stamp_fails(self):
        root = self._composed_project()
        episode = load_episode(root)
        episode["episode_title"] = "改了"
        save_episode(root, episode)
        report = validate_delivery(root, raise_on_fail=False, write_report=False)
        self.assertFalse(report["passed"])


class PipelineR2Tests(unittest.TestCase):
    """R2-P0-3: fail-fast, honest exit status, one gate registry."""

    def test_run_pipeline_stops_at_first_failure(self):
        root = _tmp()
        init_project("书", root)
        report = run_pipeline(root, stage="all")
        self.assertEqual(report["overall_status"], "failed")
        self.assertNotIn("compose-project", {step["step"] for step in report["steps"]})

    def test_check_covers_every_compose_gate(self):
        root = _tmp()
        init_project("书", root)
        report = check_project(root, stage="all")
        check_names = {item["check"] for item in report["checks"]}
        for name in formal_gate_names(schema3=True):
            self.assertIn(name, check_names)
        self.assertIn("validate-content-fill", set(SCHEMA3_DELIVERY_GATES))

    def test_fresh_project_assets_check_has_no_delivery_deadlock(self):
        root = _tmp()
        init_project("书", root)
        report = check_project(root, stage="assets")
        delivery = next(item for item in report["checks"] if item["check"] == "validate-delivery")
        self.assertEqual(delivery["status"], "passed")


class TraversalR2Tests(unittest.TestCase):
    """R2-P1-1: episode ids cannot escape the project/series root."""

    def test_add_episode_rejects_traversal(self):
        scratch = _tmp()
        series = scratch / "series"
        init_series(series, book="书")
        with self.assertRaises(ValueError):
            add_episode_project(series, episode_id="../escaped")
        self.assertFalse((scratch / "escaped").exists())

    def test_host_batch_rejects_bad_declared_id(self):
        root = _tmp()
        init_project("书", root)
        episode = load_episode(root)
        episode["episode_id"] = "../../batch-escaped"
        save_episode(root, episode)
        with self.assertRaises(ValueError):
            prepare_host_image_batch(root)
        self.assertFalse((root.parent / "batch-escaped").exists())

    def test_validate_episode_id_shapes(self):
        self.assertEqual(validate_episode_id("EP01"), "EP01")
        self.assertEqual(validate_episode_id("EP0123"), "EP0123")
        for bad in ("../x", "EP1", "EP12345", "EP01/..", "ep01", "EP01\\x"):
            with self.assertRaises(ValueError):
                validate_episode_id(bad)


class ForceInitR2Tests(unittest.TestCase):
    """R2-P1-2: force init leaves ZERO old content in the fresh tree."""

    def test_force_moves_entire_old_tree(self):
        root = _tmp()
        init_project("书", root)
        (root / "source").mkdir(exist_ok=True)
        (root / "source" / "raw_text.txt").write_text("私密原文", encoding="utf-8")
        (root / "final" / "comic.pdf").write_text("old deliverable", encoding="utf-8")
        init_project("书", root, force=True)
        self.assertFalse((root / "source" / "raw_text.txt").exists())
        self.assertFalse((root / "final" / "comic.pdf").exists())
        backup_source = list((root / "backup").glob("init-*/source/raw_text.txt"))
        self.assertTrue(backup_source and backup_source[0].read_text(encoding="utf-8") == "私密原文")


class HighConsequenceR2Tests(unittest.TestCase):
    """R2-P0-4/5: explicit declarations; high-consequence stays private."""

    def test_missing_real_person_declaration_fails_and_refuses_export(self):
        root = _tmp()
        _full_profile(root)
        profile = json.loads((root / "planning" / "grounding_profile.json").read_text(encoding="utf-8"))
        profile.pop("real_person_or_private_source")
        (root / "planning" / "grounding_profile.json").write_text(json.dumps(profile), encoding="utf-8")
        report = validate_grounding(root, require_profile=True, raise_on_fail=False)
        self.assertFalse(report["passed"])
        self.assertFalse(evaluate_export_rights(root)["public_export_allowed"])

    def test_high_consequence_requires_professional_review(self):
        root = _tmp()
        scores = {dim: 1 for dim in ("historical", "textual", "conceptual", "experiential", "rights", "cultural")}
        scores["procedural"] = 4
        _full_profile(root, scores=scores, rationales={"procedural": "含用药剂量"})
        rights = evaluate_export_rights(root)
        self.assertFalse(rights["public_export_allowed"])
        _full_profile(
            root,
            scores=scores,
            rationales={"procedural": "含用药剂量"},
            professional_review_note="张某某（执业医师）2026-07 复核全部剂量表述",
        )
        self.assertTrue(evaluate_export_rights(root)["public_export_allowed"])


class InvalidEpisodeReadR2Tests(unittest.TestCase):
    """R2-P2-10: a broken declared-3.0 episode fails at read, never demotes."""

    def test_load_rejects_broken_v3(self):
        root = _tmp()
        (root / "story").mkdir(parents=True)
        (root / "story" / "episode-001.json").write_text(
            json.dumps({"schema_version": "3.0", "book_title": 123}), encoding="utf-8"
        )
        with self.assertRaises(ValueError):
            load_episode(root)


class PackagerR2Tests(unittest.TestCase):
    """R2-P2-1: the sanctioned packager refuses dirty bundles."""

    def test_packager_emits_clean_bundle(self):
        out_dir = _tmp()
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parents[1] / "tools" / "build_release_zip.py"),
             "--out", str(out_dir), "--date", "00000000"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertGreater(payload["entries"], 200)
        import zipfile

        names = zipfile.ZipFile(payload["zip"]).namelist()
        self.assertFalse([name for name in names if "/build/" in name or ".egg-info" in name or "__pycache__" in name])
        self.assertIn("book-to-comic/tests/test_release_audit_r2.py", names)


if __name__ == "__main__":
    unittest.main()
