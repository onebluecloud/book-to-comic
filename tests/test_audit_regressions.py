"""Regression suite for the 2026-07 pre-release audit (P0/P1/P2 fixes).

Every test here maps to a numbered finding in the audit handoff; if one of
these starts failing, a shipped guarantee has regressed — do not loosen the
assertion to make it pass.
"""

from __future__ import annotations

import json
import random
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image

from book_to_comic.artifact_materializer import (
    _is_schema3_project,
    _write_artifact_production_zip,
    approve_asset,
    init_project,
)
from book_to_comic.codex_cli_bootstrap import ensure_codex_cli
from book_to_comic.grounding_qa import evaluate_export_rights, validate_grounding
from book_to_comic.image_backends import redact_url
from book_to_comic.inbox import _scan_inbox_images, import_refine
from book_to_comic.project_layout import (
    load_episode,
    new_episode_skeleton,
    resolve_episode_id,
    save_episode,
)
from book_to_comic.project_prompts import export_project_prompts
from book_to_comic.project_workflow import extract_book_to_project
from book_to_comic.review_record import (
    RECORD_STORY_TOOL,
    check_review_provenance,
    episode_sha256,
    record_story_review,
)
from book_to_comic.series import add_episode_project, init_series, series_status
from book_to_comic.skill_install import install_skill


def _tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="btc-test-"))


def _noise_image(width: int, height: int) -> Image.Image:
    rng = random.Random(42)
    image = Image.new("RGB", (width, height))
    image.putdata([(rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(width * height)])
    return image


def _write_profile(root: Path, **overrides) -> None:
    profile = {
        "schema_version": "1.0",
        "book_title": "test",
        "scores": {dim: 1 for dim in ("historical", "textual", "conceptual", "experiential", "procedural", "rights", "cultural")},
        "copyright_status": "public_domain",
        "source_edition": "某社 1999 年版",
        "real_person_or_private_source": False,
        "content_safety": {"checked": True, "hard_exclusion_hits": []},
    }
    profile.update(overrides)
    path = root / "planning" / "grounding_profile.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")


class RightsGateTests(unittest.TestCase):
    """P0-1: rights homework must gate the official path, fail closed."""

    def test_missing_profile_fails_when_required(self):
        root = _tmp()
        with self.assertRaises(ValueError):
            validate_grounding(root, require_profile=True)

    def test_missing_profile_refuses_public_export(self):
        root = _tmp()
        rights = evaluate_export_rights(root)
        self.assertFalse(rights["public_export_allowed"])

    def test_in_copyright_refuses_public_export(self):
        root = _tmp()
        _write_profile(root, copyright_status="in_copyright")
        self.assertFalse(evaluate_export_rights(root)["public_export_allowed"])

    def test_incomplete_license_fails_validation_and_export(self):
        root = _tmp()
        _write_profile(root, copyright_status="licensed", license={"rights_holder": "某社"})
        with self.assertRaises(ValueError):
            validate_grounding(root, require_profile=True)
        self.assertFalse(evaluate_export_rights(root)["public_export_allowed"])

    def test_complete_license_passes(self):
        root = _tmp()
        _write_profile(
            root,
            copyright_status="licensed",
            license={"rights_holder": "某社", "licensed_work": "某书 2020 版", "proof_note": "contract.pdf"},
        )
        report = validate_grounding(root, require_profile=True, raise_on_fail=False)
        self.assertTrue(report["passed"])
        self.assertTrue(evaluate_export_rights(root)["public_export_allowed"])

    def test_public_domain_requires_source_edition(self):
        root = _tmp()
        _write_profile(root, source_edition="")
        with self.assertRaises(ValueError):
            validate_grounding(root, require_profile=True)
        self.assertFalse(evaluate_export_rights(root)["public_export_allowed"])

    def test_real_person_requires_consent_for_export(self):
        root = _tmp()
        _write_profile(root, real_person_or_private_source=True)
        self.assertFalse(evaluate_export_rights(root)["public_export_allowed"])
        _write_profile(root, real_person_or_private_source=True, consent_note="本人 2026-01 邮件同意")
        self.assertTrue(evaluate_export_rights(root)["public_export_allowed"])


class SchemaClassificationTests(unittest.TestCase):
    """P0-4: declared schema_version is the only source of truth."""

    def _project_with_version(self, version) -> Path:
        root = _tmp()
        (root / "story").mkdir(parents=True)
        episode = new_episode_skeleton("书")
        if version is None:
            episode.pop("schema_version")
        else:
            episode["schema_version"] = version
        (root / "story" / "episode-001.json").write_text(json.dumps(episode, ensure_ascii=False), encoding="utf-8")
        return root

    def test_invalid_v3_episode_fails_closed_instead_of_demoting(self):
        root = _tmp()
        (root / "story").mkdir(parents=True)
        # Declared 3.0 but structurally broken: must raise, never classify as V2.
        (root / "story" / "episode-001.json").write_text(
            json.dumps({"schema_version": "3.0", "book_title": 123}), encoding="utf-8"
        )
        with self.assertRaises(ValueError):
            _is_schema3_project(root)

    def test_declared_v3_is_v3_even_without_planning_files(self):
        self.assertTrue(_is_schema3_project(self._project_with_version("3.0")))

    def test_declared_v2_is_v2(self):
        self.assertFalse(_is_schema3_project(self._project_with_version("2.0")))

    def test_garbage_version_fails_closed(self):
        with self.assertRaises(ValueError):
            _is_schema3_project(self._project_with_version("banana"))

    def test_legacy_missing_version_falls_back_to_sniffing(self):
        root = self._project_with_version(None)
        self.assertFalse(_is_schema3_project(root))
        (root / "planning").mkdir()
        (root / "planning" / "argument_map.json").write_text("{}", encoding="utf-8")
        self.assertTrue(_is_schema3_project(root))


class EpisodeHonestyTests(unittest.TestCase):
    """P0-3: one project = one episode; mismatched --episode errors."""

    def test_resolve_mismatch_raises(self):
        episode = {"episode_id": "EP01"}
        self.assertEqual(resolve_episode_id(episode, None), "EP01")
        self.assertEqual(resolve_episode_id(episode, "EP01"), "EP01")
        with self.assertRaises(ValueError):
            resolve_episode_id(episode, "EP02")

    def test_export_prompts_rejects_wrong_episode(self):
        root = _tmp()
        init_project("测试书", root)
        with self.assertRaises(ValueError) as ctx:
            export_project_prompts(root, episode_id="EP02")
        self.assertIn("EP02", str(ctx.exception))

    def test_series_ledger_flow(self):
        series = _tmp() / "series"
        init_series(series, book="测试书", episodes=[{"episode_id": "EP01", "title": "一"}, {"episode_id": "EP02", "title": "二"}])
        first = add_episode_project(series, episode_id="EP01")
        bible = Path(first["project_dir"]) / "planning" / "character_bible.json"
        bible.write_text(json.dumps({"characters": [{"name": "甲"}]}, ensure_ascii=False), encoding="utf-8")
        second = add_episode_project(series, episode_id="EP02")
        self.assertIn("planning/character_bible.json", second["copied_bibles"])
        ep2 = load_episode(second["project_dir"])
        self.assertEqual(ep2["episode_id"], "EP02")
        with self.assertRaises(FileExistsError):
            add_episode_project(series, episode_id="EP02")
        report = series_status(series)
        self.assertEqual(len(report["episodes"]), 2)


class InitGuardTests(unittest.TestCase):
    """P1-1: init/extract must not silently reset an existing project."""

    def test_init_refuses_then_force_backs_up(self):
        root = _tmp()
        init_project("书", root)
        (root / "manifest.json").write_text(json.dumps({"schema_version": "2.0", "project_id": "x", "assets": [{"asset_id": "keep-me"}]}), encoding="utf-8")
        with self.assertRaises(FileExistsError):
            init_project("书", root)
        self.assertIn("keep-me", (root / "manifest.json").read_text(encoding="utf-8"))
        init_project("书", root, force=True)
        backups = list((root / "backup").glob("init-*/manifest.json"))
        self.assertTrue(backups, "force must back up the old manifest")
        self.assertIn("keep-me", backups[0].read_text(encoding="utf-8"))

    def test_extract_refuses_existing_project(self):
        root = _tmp()
        init_project("书", root)
        book = root.parent / "book.txt"
        book.write_text("第一章\n正文" * 200, encoding="utf-8")
        with self.assertRaises(FileExistsError):
            extract_book_to_project(book, root)


class AtomicSaveTests(unittest.TestCase):
    """P1-2/P1-3: validate in memory first; full jsonschema; atomic replace."""

    def test_invalid_episode_never_touches_disk(self):
        root = _tmp()
        save_episode(root, new_episode_skeleton("好书"))
        before = (root / "story" / "episode-001.json").read_bytes()
        with self.assertRaises(ValueError):
            save_episode(root, {"schema_version": "3.0"})
        self.assertEqual((root / "story" / "episode-001.json").read_bytes(), before)
        self.assertFalse(list((root / "story").glob("*.tmp")))

    def test_wrong_types_rejected(self):
        root = _tmp()
        bad = new_episode_skeleton("书")
        bad["book_title"] = 123
        with self.assertRaises(ValueError):
            save_episode(root, bad)


class InboxTests(unittest.TestCase):
    """P1-4: strict filenames; no guessing which file is which panel."""

    def test_scan_requires_exact_names(self):
        inbox = _tmp()
        _noise_image(10, 10).save(inbox / "panel-01.png")
        _noise_image(10, 10).save(inbox / "final-art.png")
        with self.assertRaises(ValueError) as ctx:
            _scan_inbox_images(inbox, 2)
        message = str(ctx.exception)
        self.assertIn("missing", message)
        self.assertIn("final-art.png", message)

    def test_scan_rejects_duplicate_stems(self):
        inbox = _tmp()
        _noise_image(10, 10).save(inbox / "panel-01.png")
        _noise_image(10, 10).save(inbox / "panel-01.jpg")
        with self.assertRaises(ValueError):
            _scan_inbox_images(inbox, 1)

    def test_scan_accepts_exact_set_and_reference(self):
        inbox = _tmp()
        _noise_image(10, 10).save(inbox / "panel-01.png")
        _noise_image(10, 10).save(inbox / "panel-02.webp")
        _noise_image(10, 10).save(inbox / "character-reference.png")
        by_index, reference = _scan_inbox_images(inbox, 2)
        self.assertEqual(sorted(by_index), [1, 2])
        self.assertIsNotNone(reference)


class RefineCandidateTests(unittest.TestCase):
    """R2 P1-3/P1-4: refine imports land as CANDIDATES — no canonical or
    approved-status mutation at import time, so nothing can half-commit."""

    def _project(self) -> Path:
        root = _tmp()
        init_project("书", root)
        (root / "assets" / "panels").mkdir(parents=True, exist_ok=True)
        (root / "tmp" / "refine").mkdir(parents=True, exist_ok=True)
        for index in (1, 2):
            _noise_image(768, 1024).save(root / "assets" / "panels" / f"{index:02d}.png")
            (root / "prompts" / f"panel-{index:02d}.txt").write_text("prompt", encoding="utf-8")
        manifest = {
            "schema_version": "2.0",
            "project_id": "x",
            "assets": [
                {"asset_id": "panel-01", "version": 1, "kind": "panel", "status": "superseded", "panel_index": 1, "canonical_path": "assets/panels/01.png", "canonical_sha256": "old"},
                {"asset_id": "panel-01", "version": 2, "kind": "panel", "status": "approved", "panel_index": 1, "canonical_path": "assets/panels/01.png", "canonical_sha256": "cur"},
                {"asset_id": "panel-02", "version": 1, "kind": "panel", "status": "approved", "panel_index": 2, "canonical_path": "assets/panels/02.png", "canonical_sha256": "cur2"},
            ],
        }
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return root

    def test_partial_failure_mutates_nothing(self):
        root = self._project()
        _noise_image(768, 1024).save(root / "tmp" / "refine" / "panel-01.png")
        _noise_image(200, 200).save(root / "tmp" / "refine" / "panel-02.png")
        canonical_before = (root / "assets" / "panels" / "01.png").read_bytes()
        manifest_before = (root / "manifest.json").read_text(encoding="utf-8")
        with mock.patch("book_to_comic.artifact_materializer._require_visual_contract_gate"):
            with self.assertRaises(ValueError):
                import_refine(root)
        self.assertEqual((root / "assets" / "panels" / "01.png").read_bytes(), canonical_before)
        self.assertEqual((root / "manifest.json").read_text(encoding="utf-8"), manifest_before)
        self.assertFalse((root / "assets" / "refine-history").exists())

    def test_import_lands_candidates_and_approve_supersedes(self):
        root = self._project()
        _noise_image(768, 1024).save(root / "tmp" / "refine" / "panel-01.png")
        canonical_before = (root / "assets" / "panels" / "01.png").read_bytes()
        with mock.patch("book_to_comic.artifact_materializer._require_visual_contract_gate"):
            report = import_refine(root)
        self.assertEqual(report["status"], "refine-candidates-imported")
        # Import touched neither the canonical file nor any approved status.
        self.assertEqual((root / "assets" / "panels" / "01.png").read_bytes(), canonical_before)
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        entries = [item for item in manifest["assets"] if item.get("panel_index") == 1]
        self.assertEqual([e["status"] for e in entries], ["superseded", "approved", "candidate"])
        self.assertEqual(entries[2]["source_mode"], "refine-inbox")
        # Explicit approve replaces the canonical and supersedes the old version.
        approve_asset(root, "panel-01", "对照原版：构图/角色一致，质感提升")
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        approved = [item for item in manifest["assets"] if item.get("panel_index") == 1 and item["status"] == "approved"]
        self.assertEqual(len(approved), 1)
        self.assertEqual(approved[0]["version"], 3)
        self.assertNotEqual((root / "assets" / "panels" / "01.png").read_bytes(), canonical_before)

    def test_approve_state_machine(self):
        root = self._project()
        _noise_image(768, 1024).save(root / "tmp" / "refine" / "panel-01.png")
        with mock.patch("book_to_comic.artifact_materializer._require_visual_contract_gate"):
            import_refine(root)
        with self.assertRaises(ValueError):
            approve_asset(root, "panel-01", "   ")
        approve_asset(root, "panel-01", "看过，一致")
        with self.assertRaises(ValueError):
            approve_asset(root, "panel-01", "再批一次")


class PublicBundleTests(unittest.TestCase):
    """P0-5: the public/private bundles never contain source/planning/prompts."""

    def _project(self) -> Path:
        root = _tmp()
        for relative in ("source/raw_text.txt", "planning/series_bible.json", "prompts/panel-01.txt", "assets/panels/01.png", "final/comic.pdf", "qa/delivery-gate.json"):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x", encoding="utf-8")
        return root

    def test_public_bundle_excludes_working_files(self):
        root = self._project()
        archive = _write_artifact_production_zip(root, root / "final" / "production.zip", include_debug=False, bundle_kind="public")
        names = zipfile.ZipFile(archive).namelist()
        self.assertFalse([name for name in names if name.startswith(("source/", "planning/", "prompts/"))], names)
        self.assertIn("assets/panels/01.png", names)

    def test_debug_bundle_includes_them_and_says_so(self):
        root = self._project()
        archive = _write_artifact_production_zip(root, root / "final" / "production-debug.zip", include_debug=True, bundle_kind="debug")
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            manifest = json.loads(bundle.read("production-manifest.json"))
        self.assertIn("source/raw_text.txt", names)
        self.assertEqual(manifest["bundle"], "debug")


class RedactionTests(unittest.TestCase):
    """P1-6: no credentials in diagnostics."""

    def test_userinfo_and_query_are_stripped(self):
        redacted = redact_url("http://user:hunter2@10.0.0.5:8188/api?token=sekrit#frag")
        self.assertNotIn("hunter2", redacted)
        self.assertNotIn("sekrit", redacted)
        self.assertEqual(redacted, "http://10.0.0.5:8188")

    def test_non_url_value_not_echoed(self):
        self.assertEqual(redact_url("just-a-password"), "<non-url-value>")


class ReviewRecordTests(unittest.TestCase):
    """P0-2: reviews only exist via record commands; stale reviews die."""

    def _project_with_episode(self) -> Path:
        root = _tmp()
        init_project("书", root)
        return root

    def test_self_review_rejected(self):
        with self.assertRaises(ValueError):
            record_story_review(
                self._project_with_episode(),
                author_pass_id="same",
                reviewer_pass_id="same",
                reviewer_kind="human",
                evidence_file="unused.json",
            )

    def test_approved_review_needs_required_checks_and_evidence(self):
        root = self._project_with_episode()
        evidence = root / "review.json"
        evidence.write_text(json.dumps({"checks": [{"name": "中文叠字校对", "status": "passed", "evidence": []}]}), encoding="utf-8")
        with self.assertRaises(ValueError):
            record_story_review(root, author_pass_id="a", reviewer_pass_id="b", reviewer_kind="human", evidence_file=evidence)

    def test_provenance_freshness(self):
        root = self._project_with_episode()
        report = {
            "provenance": {
                "recorded_by": RECORD_STORY_TOOL,
                "reviewer_kind": "human",
                "episode_sha256": episode_sha256(root),
            }
        }
        self.assertEqual(check_review_provenance(report, expected_tool=RECORD_STORY_TOOL, project=root), [])
        # Hand-written report: no stamp.
        self.assertTrue(check_review_provenance({}, expected_tool=RECORD_STORY_TOOL, project=root))
        # Episode changed after recording: stale.
        episode = load_episode(root)
        episode["episode_title"] = "改了"
        save_episode(root, episode)
        problems = check_review_provenance(report, expected_tool=RECORD_STORY_TOOL, project=root)
        self.assertTrue(any("stale" in problem for problem in problems))


class BootstrapOptInTests(unittest.TestCase):
    """P2-6: npm auto-install requires explicit opt-in and stays pinned."""

    def test_install_refused_without_env(self):
        tools = _tmp()
        with mock.patch("book_to_comic.codex_cli_bootstrap.shutil.which", return_value=None), mock.patch.dict(
            "os.environ", {}, clear=False
        ):
            import os

            os.environ.pop("BOOK_TO_COMIC_ALLOW_NPM_INSTALL", None)
            report = ensure_codex_cli(install=True, tools_dir=tools)
        self.assertEqual(report["install_status"], "refused")
        self.assertFalse(report["install_attempted"])

    def test_package_is_pinned(self):
        from book_to_comic.codex_cli_bootstrap import CODEX_PACKAGE

        self.assertIn("@", CODEX_PACKAGE.replace("@openai/", "", 1))


class SkillInstallTests(unittest.TestCase):
    """P2-1: install-skill works from a source checkout by default."""

    def test_install_into_project_scope(self):
        project = _tmp()
        destinations = install_skill("claude", scope="project", project_dir=project)
        self.assertEqual(len(destinations), 1)
        self.assertTrue((destinations[0] / "SKILL.md").is_file())
        self.assertTrue((destinations[0] / "book_to_comic" / "cli.py").is_file())
        self.assertFalse((destinations[0] / ".git").exists())


class VersionTests(unittest.TestCase):
    """P2-14: one release version everywhere."""

    def test_version_consistency(self):
        import book_to_comic

        root = Path(__file__).resolve().parents[1]
        pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn(f'version = "{book_to_comic.__version__}"', pyproject)
        skill = (root / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn(book_to_comic.__version__, skill)


if __name__ == "__main__":
    unittest.main()
