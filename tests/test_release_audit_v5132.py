"""Regression suite for the 2026-07-13 v5.13.2 release audit.

Every test reproduces a failure that audit demonstrated against v5.13.2;
loosening any assertion re-opens a shipped hole.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image

from book_to_comic.artifact_materializer import (
    approve_asset,
    init_project,
    materialize_image,
)
from book_to_comic.delivery_gate import (
    record_bundle_manifest,
    stamp_delivery,
    validate_delivery,
)


def _tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="btc-v5132-"))


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


def _write_zip(path: Path, payload: bytes = b"x") -> None:
    import zipfile

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("payload.txt", payload)


class BundlePromiseTests(unittest.TestCase):
    """v5.13.2 P0-1: a successful stamp PROMISES the archive + sidecar."""

    def _composed(self) -> Path:
        root = _tmp()
        init_project("书", root)
        _full_profile(root)
        (root / "final" / "comic.pdf").write_text("pdf", encoding="utf-8")
        stamp_delivery(
            root, gates=["g"], panel_count=1, public_export_allowed=True,
            expected_bundle_name="production.zip", expected_bundle_tier="public",
        )
        bundle = root / "final" / "production.zip"
        _write_zip(bundle)
        record_bundle_manifest(root, bundle, bundle_kind="public")
        return root

    def test_intact_promise_passes(self):
        root = self._composed()
        self.assertTrue(validate_delivery(root, raise_on_fail=False, write_report=False)["passed"])

    def test_deleting_zip_and_sidecar_together_fails(self):
        root = self._composed()
        (root / "final" / "production.zip").unlink()
        (root / "qa" / "bundle-manifest.json").unlink()
        report = validate_delivery(root, raise_on_fail=False, write_report=False)
        self.assertFalse(report["passed"])
        self.assertTrue(any("bundle-manifest.json is missing" in issue for issue in report["issues"]))

    def test_stamp_without_archive_commit_fails(self):
        # The crash window: stamp written, ZIP/sidecar never written.
        root = _tmp()
        init_project("书", root)
        _full_profile(root)
        (root / "final" / "comic.pdf").write_text("pdf", encoding="utf-8")
        stamp_delivery(
            root, gates=["g"], panel_count=1, public_export_allowed=True,
            expected_bundle_name="production.zip", expected_bundle_tier="public",
        )
        report = validate_delivery(root, raise_on_fail=False, write_report=False)
        self.assertFalse(report["passed"])

    def test_tier_tamper_fails(self):
        root = self._composed()
        manifest_path = root / "qa" / "bundle-manifest.json"
        record = json.loads(manifest_path.read_text(encoding="utf-8"))
        record["bundle"]["tier"] = "private"
        manifest_path.write_text(json.dumps(record), encoding="utf-8")
        report = validate_delivery(root, raise_on_fail=False, write_report=False)
        self.assertFalse(report["passed"])


class DraftMasqueradeTests(unittest.TestCase):
    """v5.13.2 P0-3: drafts can never look like gated production output."""

    def test_non_artifact_dir_is_not_applicable(self):
        root = _tmp()
        (root / "final").mkdir(parents=True)
        (root / "final" / "comic.pdf").write_text("draft", encoding="utf-8")
        report = validate_delivery(root, raise_on_fail=False, write_report=False)
        self.assertFalse(report["applicable"])
        self.assertEqual(report["status"], "not-applicable")

    def test_export_delivery_refuses_production_names(self):
        from book_to_comic.delivery import export_cards_delivery

        root = _tmp()
        cards = root / "cards"
        cards.mkdir(parents=True)
        Image.new("RGB", (96, 128), (50, 60, 70)).save(cards / "01.png")
        with self.assertRaises(ValueError):
            export_cards_delivery(cards, root / "production.zip", "zip-production")
        out = export_cards_delivery(cards, root / "draft-pack.zip", "zip-production")
        import zipfile

        with zipfile.ZipFile(out) as archive:
            manifest = json.loads(archive.read("manifest.json"))
        self.assertEqual(manifest["bundle"], "draft")
        self.assertEqual(manifest["gates"], "none")

    def test_series_status_marks_broken_project_invalid(self):
        from book_to_comic.series import add_episode_project, init_series, series_status

        series = _tmp()
        init_series(series, book="书")
        result = add_episode_project(series, episode_id="EP01")
        ep_root = Path(result["project_dir"])
        (ep_root / "final" / "comic.pdf").write_text("x", encoding="utf-8")
        (ep_root / "project.json").unlink()
        status = series_status(series)
        ep = next(item for item in status["episodes"] if item["episode_id"] == "EP01")
        self.assertEqual(ep["derived_status"], "invalid-project")


class AssetHistoryTests(unittest.TestCase):
    """v5.13.2 P0-4: append-only versions, hash-checked approval, atomic commit."""

    def _project(self) -> Path:
        root = _tmp()
        init_project("书", root)
        return root

    def _materialize(self, root: Path, version: int):
        src = root / "tmp" / f"in-{version}.png"
        src.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (800, 1066), (version * 20 % 255, 90, 40)).save(src)
        prompt = root / "prompts" / "character-reference.txt"
        prompt.parent.mkdir(parents=True, exist_ok=True)
        prompt.write_text("prompt", encoding="utf-8")
        return materialize_image(
            project=root, kind="character-reference", asset_id="character-reference",
            version=version, snapshot=root / "tmp", prompt=prompt, source=src,
        )

    def test_version_replay_is_rejected(self):
        from book_to_comic.artifact_materializer import reject_asset

        root = self._project()
        self._materialize(root, 1)
        reject_asset(root, "character-reference", "构图错误")
        with self.assertRaises(ValueError):
            self._materialize(root, 1)  # replaying v1 must not erase the rejection
        self._materialize(root, 2)  # the legal path

    def test_version_must_be_sequential(self):
        root = self._project()
        self._materialize(root, 1)
        with self.assertRaises(ValueError):
            self._materialize(root, 5)

    def test_swapped_candidate_cannot_be_approved(self):
        root = self._project()
        item = self._materialize(root, 1)
        candidate = root / str(item["candidate_path"])
        Image.new("RGB", (800, 1066), (1, 2, 3)).save(candidate)  # swap after materialize
        with self.assertRaises(ValueError) as ctx:
            approve_asset(root, "character-reference", "看过")
        self.assertIn("changed after materialize", str(ctx.exception))

    def test_manifest_write_failure_rolls_canonical_back(self):
        root = self._project()
        self._materialize(root, 1)
        canonical = root / "assets" / "references" / "character-reference.png"
        with mock.patch("book_to_comic.artifact_materializer._write_manifest", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                approve_asset(root, "character-reference", "看过")
        self.assertFalse(canonical.exists(), "canonical must be rolled back when the manifest commit fails")
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["assets"][0]["status"], "candidate")


class ContentSafetyGateTests(unittest.TestCase):
    """v5.13.2 P1-4: hard exclusions are a machine-checked record, not prose."""

    def test_missing_record_fails_grounding(self):
        from book_to_comic.grounding_qa import validate_grounding

        root = _tmp()
        _full_profile(root)
        profile = json.loads((root / "planning" / "grounding_profile.json").read_text(encoding="utf-8"))
        del profile["content_safety"]
        (root / "planning" / "grounding_profile.json").write_text(json.dumps(profile), encoding="utf-8")
        with self.assertRaises(ValueError):
            validate_grounding(root, require_profile=True)

    def test_hit_blocks_every_bundle_tier(self):
        from book_to_comic.grounding_qa import evaluate_export_rights

        root = _tmp()
        _full_profile(root, content_safety={"checked": True, "hard_exclusion_hits": ["self-harm-methods"]})
        rights = evaluate_export_rights(root)
        self.assertFalse(rights["public_export_allowed"])
        self.assertEqual(rights["hard_exclusion_hits"], ["self-harm-methods"])

    def test_clean_record_passes(self):
        from book_to_comic.grounding_qa import validate_grounding

        root = _tmp()
        _full_profile(root)
        report = validate_grounding(root, require_profile=True, raise_on_fail=False)
        self.assertTrue(report["passed"])


class InitProtectionTests(unittest.TestCase):
    """v5.13.2 P1-2: any non-empty target refuses; backups never merge."""

    def test_non_marker_private_file_refuses_init(self):
        root = _tmp()
        (root / "source").mkdir(parents=True)
        (root / "source" / "private.txt").write_text("秘密", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            init_project("书", root)

    def test_force_backups_never_merge(self):
        root = _tmp()
        init_project("书", root)
        init_project("书", root, force=True)
        init_project("书", root, force=True)
        backups = [p for p in (root / "backup").iterdir() if p.is_dir()]
        self.assertEqual(len(backups), 2, "each --force must produce its own backup generation")
        for backup in backups:
            self.assertTrue((backup / "project.json").is_file())


class PanelCountContractTests(unittest.TestCase):
    """v5.13.2 P1-5: story and approved assets agree on ONE panel count."""

    def test_asset_count_must_match_story(self):
        import hashlib

        from book_to_comic.artifact_materializer import validate_project_assets

        root = _tmp()
        init_project("书", root)
        panels = root / "assets" / "panels"
        panels.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (96, 128), (5, 5, 5)).save(panels / "01.png")
        sha = hashlib.sha256((panels / "01.png").read_bytes()).hexdigest()
        entry = {
            "kind": "panel", "status": "approved", "panel_index": 1,
            "asset_id": "panel-01", "canonical_path": "assets/panels/01.png", "canonical_sha256": sha,
        }
        (root / "manifest.json").write_text(json.dumps({"schema_version": "2.0", "assets": [entry]}), encoding="utf-8")
        with mock.patch("book_to_comic.artifact_materializer.flatten_episode_panels", return_value=[{}, {}]):
            with self.assertRaises(ValueError) as ctx:
                validate_project_assets(root)
        self.assertIn("does not match the official episode", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
