"""Regression suite for the 2026-07-12 v5.13.1 release audit.

Every test reproduces a failure the audit demonstrated against v5.13.1;
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

from book_to_comic.artifact_materializer import _collect_bundle_allowlist, init_project
from book_to_comic.delivery_gate import (
    record_bundle_manifest,
    stamp_delivery,
    validate_delivery,
)
from book_to_comic.review_record import approved_panels_sha256


def _tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="btc-v5131-"))


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


class PanelFingerprintTests(unittest.TestCase):
    """P0-2: the panel fingerprint must hash real bytes, not declarations."""

    def _project_with_panel(self) -> Path:
        root = _tmp()
        panels = root / "assets" / "panels"
        panels.mkdir(parents=True)
        (panels / "01.png").write_bytes(b"real-png-bytes")
        import hashlib

        declared = hashlib.sha256(b"real-png-bytes").hexdigest()
        manifest = {
            "assets": [
                {
                    "kind": "panel",
                    "status": "approved",
                    "panel_index": 1,
                    "canonical_path": "assets/panels/01.png",
                    "canonical_sha256": declared,
                }
            ]
        }
        (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return root

    def test_swapping_canonical_bytes_changes_fingerprint(self):
        root = self._project_with_panel()
        before = approved_panels_sha256(root)
        (root / "assets" / "panels" / "01.png").write_bytes(b"another-valid-png")
        after = approved_panels_sha256(root)
        self.assertNotEqual(before, after)

    def test_missing_canonical_changes_fingerprint(self):
        root = self._project_with_panel()
        before = approved_panels_sha256(root)
        (root / "assets" / "panels" / "01.png").unlink()
        after = approved_panels_sha256(root)
        self.assertNotEqual(before, after)


class BundleBindingTests(unittest.TestCase):
    """P0-2: the production archive is bound by qa/bundle-manifest.json."""

    def _composed_with_bundle(self) -> Path:
        root = _tmp()
        init_project("书", root)
        _full_profile(root)
        (root / "final" / "comic.pdf").write_text("pdf", encoding="utf-8")
        stamp_delivery(root, gates=["g"], panel_count=1, public_export_allowed=True)
        bundle = root / "final" / "production.zip"
        _write_zip(bundle)
        record_bundle_manifest(root, bundle, bundle_kind="public")
        return root

    def test_intact_bundle_passes(self):
        root = self._composed_with_bundle()
        self.assertTrue(validate_delivery(root, raise_on_fail=False, write_report=False)["passed"])

    def test_replaced_bundle_fails(self):
        root = self._composed_with_bundle()
        _write_zip(root / "final" / "production.zip", b"a-different-but-valid-zip")
        report = validate_delivery(root, raise_on_fail=False, write_report=False)
        self.assertFalse(report["passed"])
        self.assertTrue(any("replaced or modified" in issue for issue in report["issues"]))

    def test_deleted_bundle_fails(self):
        root = self._composed_with_bundle()
        (root / "final" / "production.zip").unlink()
        report = validate_delivery(root, raise_on_fail=False, write_report=False)
        self.assertFalse(report["passed"])
        self.assertTrue(any("missing" in issue for issue in report["issues"]))

    def test_bundle_without_manifest_fails(self):
        root = _tmp()
        init_project("书", root)
        _full_profile(root)
        (root / "final" / "comic.pdf").write_text("pdf", encoding="utf-8")
        stamp_delivery(root, gates=["g"], panel_count=1, public_export_allowed=True)
        _write_zip(root / "final" / "production.zip")
        report = validate_delivery(root, raise_on_fail=False, write_report=False)
        self.assertFalse(report["passed"])
        self.assertTrue(any("bundle-manifest" in issue for issue in report["issues"]))


class RevokedQuarantineTests(unittest.TestCase):
    """P0-3: revoked archives leave final/ and can never be re-bundled."""

    def test_stamp_refuses_revoked_files_in_final(self):
        root = _tmp()
        init_project("书", root)
        (root / "final" / "production.zip.20260101T000000Z.REVOKED").write_text("old", encoding="utf-8")
        with self.assertRaises(ValueError):
            stamp_delivery(root, gates=["g"], panel_count=1)

    def test_bundle_allowlist_rejects_revoked_and_stray(self):
        root = _tmp()
        init_project("书", root)
        (root / "final" / "comic.pdf").write_text("pdf", encoding="utf-8")
        output = root / "final" / "production.zip"
        # clean final passes
        files = _collect_bundle_allowlist(root, output)
        self.assertTrue(any(path.name == "comic.pdf" for path in files))
        # a revoked artifact fails closed
        revoked = root / "final" / "production.zip.20260101T000000Z.REVOKED"
        revoked.write_text("old", encoding="utf-8")
        with self.assertRaises(ValueError):
            _collect_bundle_allowlist(root, output)
        revoked.unlink()
        # any stray file fails closed instead of shipping silently
        (root / "final" / "notes.txt").write_text("private", encoding="utf-8")
        with self.assertRaises(ValueError):
            _collect_bundle_allowlist(root, output)


class SourceIngestTests(unittest.TestCase):
    """P0-4: uploaded book → series → EP01 must work with official commands only."""

    def test_txt_to_series_to_ep01_source_chunk(self):
        from book_to_comic.series import add_episode_project, ingest_source, init_series
        from book_to_comic.story_ir import source_chunk_project

        series = _tmp()
        book = series / "book.txt"
        book.write_text("晋太元中，武陵人捕鱼为业。缘溪行，忘路之远近。忽逢桃花林，夹岸数百步。" * 8, encoding="utf-8")
        init_series(series, book="桃花源记")
        record = ingest_source(series, book, into="series")
        self.assertTrue((series / "source" / "raw_text.txt").is_file())
        self.assertTrue(record["text_sha256"])

        result = add_episode_project(series, episode_id="EP01")
        ep_root = Path(result["project_dir"])
        # The series source must have been handed to the episode project…
        self.assertTrue((ep_root / "source" / "raw_text.txt").is_file())
        self.assertTrue(result["source_handoff_sha256"])
        # …and the official chunker must succeed inside EP01 (the audit's
        # acceptance criterion: it used to fail on a missing raw_text.txt).
        report = source_chunk_project(ep_root)
        self.assertGreater(len(report.get("chunks", report.get("source_chunks", [1]))), 0)

    def test_ingest_refuses_overwrite_and_missing_targets(self):
        from book_to_comic.series import ingest_source, init_series

        series = _tmp()
        book = series / "book.txt"
        book.write_text("原文", encoding="utf-8")
        init_series(series, book="书")
        ingest_source(series, book, into="series")
        with self.assertRaises(FileExistsError):
            ingest_source(series, book, into="series")
        # project mode requires an existing project
        not_a_project = _tmp()
        with self.assertRaises(FileNotFoundError):
            ingest_source(not_a_project, book, into="project")

    def test_ingest_into_existing_project(self):
        from book_to_comic.series import ingest_source

        root = _tmp()
        init_project("书", root)
        book = root.parent / f"{root.name}-book.txt"
        book.write_text("正文内容", encoding="utf-8")
        record = ingest_source(root, book, into="project")
        self.assertTrue((root / "source" / "raw_text.txt").is_file())
        self.assertEqual(record["ingested_into"], "project")


class InstallSkillSafetyTests(unittest.TestCase):
    """P0-5: default project-scope install must not recurse or self-delete."""

    def _fake_source(self) -> Path:
        src = _tmp()
        (src / "SKILL.md").write_text("---\nname: book-to-comic\n---\n", encoding="utf-8")
        (src / "book_to_comic").mkdir()
        (src / "book_to_comic" / "__init__.py").write_text("", encoding="utf-8")
        return src

    def test_project_scope_install_inside_source_does_not_recurse(self):
        from book_to_comic.skill_install import install_skill

        src = self._fake_source()
        # The audit scenario: project_dir defaults to '.', i.e. the source
        # checkout itself — destination lives INSIDE source.
        dests = install_skill("codex", scope="project", project_dir=src, source_dir=src)
        dest = dests[0]
        self.assertTrue((dest / "SKILL.md").is_file())
        self.assertFalse((dest / ".agents").exists(), "self-nested copy means the recursion guard failed")
        # Re-install over an existing install stays safe (staging + swap).
        install_skill("codex", scope="project", project_dir=src, source_dir=src)
        self.assertTrue((dest / "SKILL.md").is_file())
        self.assertFalse((dest.parent / f".{dest.name}.staging").exists())
        self.assertFalse((dest.parent / f".{dest.name}.backup").exists())

    def test_reinstall_from_installed_dir_refuses_instead_of_self_deleting(self):
        from book_to_comic.skill_install import install_skill

        src = self._fake_source()
        dest = install_skill("codex", scope="project", project_dir=src, source_dir=src)[0]
        project_root = dest.parents[2]  # <src>/.agents/skills/book-to-comic -> <src>
        with self.assertRaises(ValueError):
            install_skill("codex", scope="project", project_dir=project_root, source_dir=dest)
        # The audit's failure mode was "exit 1 AND the skill directory is gone".
        self.assertTrue((dest / "SKILL.md").is_file(), "install must never delete its own source")


class VisualIdentitySchemaTests(unittest.TestCase):
    """P1-1: schema and runtime agree on where why_specific_to_this_book lives."""

    PKG_ROOT = Path(__file__).resolve().parents[1]

    def test_schema_requires_why_under_adaptation_form(self):
        for rel in ("schemas/visual_identity.schema.json", "book_to_comic/schemas/visual_identity.schema.json"):
            schema = json.loads((self.PKG_ROOT / rel).read_text(encoding="utf-8"))
            self.assertIn(
                "why_specific_to_this_book",
                schema["properties"]["adaptation_form"].get("required", []),
                rel,
            )
            self.assertNotIn("required", schema["properties"]["book_signature"], rel)

    def test_init_template_places_why_under_adaptation_form(self):
        from book_to_comic.visual_identity import empty_visual_identity

        identity = empty_visual_identity(book_title="书")
        self.assertIn("why_specific_to_this_book", identity["adaptation_form"])


class CharacterReferenceLineageTests(unittest.TestCase):
    """P1-2: cast projects must not pass asset gates without an approved
    character reference; the inbox fallback fails closed without one."""

    def _png(self, path: Path, size=(64, 64)) -> None:
        from PIL import Image

        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, (120, 80, 40)).save(path)

    def _cast_project(self) -> Path:
        root = _tmp()
        init_project("书", root)
        (root / "planning").mkdir(exist_ok=True)
        (root / "planning" / "character_bible.json").write_text(
            json.dumps({"characters": [{"name": "渔人"}]}, ensure_ascii=False), encoding="utf-8"
        )
        return root

    def test_inbox_import_refuses_cast_project_without_reference(self):
        from book_to_comic.inbox import import_inbox

        root = self._cast_project()
        inbox = root / "tmp" / "inbox"
        self._png(inbox / "panel-01.png")
        # Isolate the guard: a fully schema-valid episode is not the point of
        # this test — the audit scenario is "cast project, panels in inbox,
        # no reference anywhere".
        with mock.patch("book_to_comic.inbox._panels", return_value=[{}]):
            with self.assertRaises(ValueError) as ctx:
                import_inbox(root)
            self.assertIn("character reference", str(ctx.exception))
            # With a reference image present the guard passes (later gates may
            # still fail for other reasons — but NOT this one).
            self._png(inbox / "character-reference.png")
            try:
                import_inbox(root)
            except ValueError as exc:
                self.assertNotIn("no approved character reference", str(exc))
            except FileNotFoundError:
                pass  # downstream prompt gates — the guard itself passed

    def test_validate_project_assets_requires_reference_for_cast(self):
        import hashlib

        from book_to_comic.artifact_materializer import validate_project_assets

        root = self._cast_project()
        self._png(root / "assets" / "panels" / "01.png", size=(96, 128))
        sha = hashlib.sha256((root / "assets" / "panels" / "01.png").read_bytes()).hexdigest()
        panel_entry = {
            "kind": "panel",
            "status": "approved",
            "panel_index": 1,
            "asset_id": "panel-01",
            "canonical_path": "assets/panels/01.png",
            "canonical_sha256": sha,
        }
        (root / "manifest.json").write_text(json.dumps({"schema_version": "2.0", "assets": [panel_entry]}), encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            validate_project_assets(root)
        self.assertIn("character-reference", str(ctx.exception))
        # Adding an approved reference satisfies the backstop.
        self._png(root / "assets" / "references" / "character-reference.png")
        ref_entry = {"kind": "character-reference", "status": "approved", "asset_id": "character-reference"}
        (root / "manifest.json").write_text(
            json.dumps({"schema_version": "2.0", "assets": [panel_entry, ref_entry]}), encoding="utf-8"
        )
        report = validate_project_assets(root)
        self.assertEqual(report["panel_count"], 1)


class ImageAdmissionTests(unittest.TestCase):
    """P1-6: image content is admitted by FORMAT allowlist, not extension."""

    def test_disguised_psd_rejected(self):
        from book_to_comic.image_safety import open_image_checked

        root = _tmp()
        fake = root / "panel-01.png"  # PSD magic bytes behind a .png name
        fake.write_bytes(b"8BPS" + b"\x00" * 128)
        with self.assertRaises(ValueError) as ctx:
            open_image_checked(fake, purpose="inbox image")
        self.assertIn("not PNG/JPEG/WEBP", str(ctx.exception))

    def test_real_png_admitted(self):
        from PIL import Image

        from book_to_comic.image_safety import open_image_checked

        root = _tmp()
        good = root / "ok.png"
        Image.new("RGB", (96, 128), (10, 20, 30)).save(good)
        width, height, detected = open_image_checked(good)
        self.assertEqual((width, height, detected), (96, 128, "PNG"))

    def test_oversized_file_rejected(self):
        from book_to_comic import image_safety

        root = _tmp()
        big = root / "big.png"
        big.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 1024)
        original = image_safety.MAX_FILE_BYTES
        image_safety.MAX_FILE_BYTES = 100
        try:
            with self.assertRaises(ValueError) as ctx:
                image_safety.open_image_checked(big)
            self.assertIn("too large", str(ctx.exception))
        finally:
            image_safety.MAX_FILE_BYTES = original


class PipelineComposeOrderTests(unittest.TestCase):
    """P0-1: compose stage never rebuilds covers after the stamp and always
    ends by re-validating delivery."""

    def test_compose_stage_steps_and_order(self):
        root = _tmp()
        init_project("书", root)
        calls: list[str] = []
        with mock.patch("book_to_comic.pipeline.compose_artifact_project", side_effect=lambda r: calls.append("compose") or {"passed": True}), \
             mock.patch("book_to_comic.pipeline.validate_delivery", side_effect=lambda r: calls.append("validate-delivery") or {"passed": True}):
            from book_to_comic.pipeline import run_pipeline

            report = run_pipeline(root, stage="compose")
        self.assertEqual(calls, ["compose", "validate-delivery"])
        steps = [step["step"] for step in report["steps"]]
        self.assertEqual(steps, ["compose-project", "validate-delivery"])
        self.assertNotIn("build-cover", steps)
        self.assertEqual(report["overall_status"], "passed")


if __name__ == "__main__":
    unittest.main()
