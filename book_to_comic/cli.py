import argparse
import json
from pathlib import Path
import sys

from .capabilities import capabilities_json
from .character_design import CharacterDesignError, validate_character_bible
from .codex_cli_bootstrap import ensure_codex_cli
from .comic_image import render_thinking_fast_and_slow_comic
from .composer import (
    build_review_package,
    compose_carousel_card_images,
    compose_long_image,
    extract_panels_from_grid,
    validate_panel_images,
)
from .delivery import DELIVERY_FORMATS, export_cards_delivery
from .engine import build_adaptation_prompt, build_sample_package, render_manual_package
from .environment_design import EnvironmentDesignError, validate_environment_bible
from .final_pipeline import generate_final_comic
from .host_image_batch import prepare_host_image_batch
from .image_backends import probe_image_backends
from .image_assets import import_host_image_panels
from .art_style import set_custom_art_style
from .consistency_sheet import build_consistency_sheets
from .inbox import import_inbox, import_refine, prepare_inbox, prepare_refine
from .upscale import upscale_project_panels
from .package_io import package_from_json, validate_package
from .quick import quick_comic
from .prompt_files import export_manual_prompt_files
from .art_bible import read_art_bible
from .artifact_materializer import (
    approve_asset,
    compose_artifact_project,
    init_project,
    materialize_image,
    recover_session_image,
    reject_asset,
    snapshot_images,
    validate_project_assets,
    validate_project_balloon_plan,
)
from .appeal import AppealGateError, validate_appeal
from .argument_map import ArgumentMapError, export_argument_planning_prompt, validate_argument_map
from .character_qa import CharacterAgencyError, export_character_prompts, validate_character_design
from .conflict_gate import ConflictGateError, validate_conflict
from .delivery_gate import COMPLETION_STATE_DELIVERED, validate_delivery
from .delivery_config import project_panel_aspect_ratio
from .cover import build_cover_assets
from .fit import FitValidationError, validate_fit
from .models import PanelArtSpec
from .migrations import MigrationError, migrate_project
from .page_qa import PagePlanError, validate_page_plan
from .pipeline import check_project, run_pipeline
from .prompt_compiler import compile_panel_prompt
from .narrative_identity import NarrativeIdentityError, validate_narrative_identity
from .project_layout import load_episode, migrate_legacy_project
from .project_prompts import export_project_prompts, export_project_text_prompts
from .project_workflow import (
    compose_project,
    export_project,
    extract_book_to_project,
    render_project,
    validate_project,
)
from .regeneration_audit import RegenerationAuditError, audit_regeneration
from .skill_install import install_skill
from .source_claims import SourceClaimError, validate_source_claims
from .source_fidelity import SourceFidelityError, validate_source_fidelity
from .story_gate import StoryGateError, validate_story_gate
from .story_ir import build_story_ir, source_chunk_project, validate_source_coverage
from .lettering_qa import LetteringLayoutError, validate_lettering_layout
from .text_distinctiveness import TextDistinctivenessError, validate_text_distinctiveness
from .text_qa import LetteringFidelityError, validate_lettering_fidelity, validate_text_richness
from .styles import choose_random_style, get_style, iter_styles, list_style_ids, load_style_registry, style_show
from .visual_distinctiveness import DistinctivenessError, validate_distinctiveness
from .visual_contract import build_visual_contract, validate_visual_contract
from .visual_identity import VisualIdentityError, validate_visual_identity
from .world_model import WorldModelError, export_environment_prompts
from .world_qa import WorldSpecificityError, validate_world_specificity


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "doctor":
        sys.stdout.write(capabilities_json())
        return 0

    if args.command == "init-project":
        try:
            path = init_project(
                args.book,
                args.project_dir,
                delivery_intent=args.delivery_intent,
                episode_id=args.episode_id,
                force=args.force,
            )
        except (OSError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(f"Initialized project: {path}")
        return 0

    if args.command == "init-series":
        from .series import init_series

        try:
            episodes = []
            for chunk in (args.episodes or "").split(","):
                chunk = chunk.strip()
                if not chunk:
                    continue
                episode_id, _, title = chunk.partition(":")
                episodes.append({"episode_id": episode_id.strip(), "title": title.strip()})
            data = init_series(args.dir, book=args.book, episodes=episodes or None)
        except (OSError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(f"Series ledger created: {args.dir}/series.json with {len(data['episodes'])} planned episode(s).")
        return 0

    if args.command == "ingest-source":
        from .series import ingest_source

        try:
            record = ingest_source(
                args.series if args.series else args.project,
                args.input,
                into="series" if args.series else "project",
            )
        except (OSError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return 0

    if args.command == "add-episode":
        from .series import add_episode_project

        try:
            result = add_episode_project(
                args.series,
                episode_id=args.episode,
                project_dir=args.project_dir,
                copy_bibles_from=args.copy_bibles_from,
                delivery_intent=args.delivery_intent,
            )
        except (OSError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "series-status":
        from .series import series_status

        try:
            report = series_status(args.series)
        except (OSError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "migrate-legacy-project":
        try:
            result = migrate_legacy_project(args.project)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "migrate-project":
        try:
            result = migrate_project(args.project, to_version=args.to_version)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError, MigrationError) as exc:
            print(f"Migration failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "snapshot-images":
        try:
            path = snapshot_images(args.output)
        except (OSError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(f"Wrote image snapshot: {path}")
        return 0

    if args.command == "recover-session-image":
        try:
            path = recover_session_image(args.session, args.output)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(f"Recovered session image: {path}")
        return 0

    if args.command == "materialize-image":
        try:
            item = materialize_image(
                project=args.project,
                kind=args.kind,
                asset_id=args.asset_id,
                version=args.version,
                snapshot=args.snapshot,
                prompt=args.prompt,
                panel_index=args.panel_index,
                reference_assets=args.reference_asset or [],
                source=args.source,
            )
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(item, ensure_ascii=False, indent=2))
        return 0

    if args.command == "approve-asset":
        try:
            item = approve_asset(args.project, args.asset_id, args.qa_summary)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(item, ensure_ascii=False, indent=2))
        return 0

    if args.command == "reject-asset":
        try:
            item = reject_asset(args.project, args.asset_id, args.qa_summary)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(item, ensure_ascii=False, indent=2))
        return 0

    if args.command == "validate-project-assets":
        try:
            report = validate_project_assets(args.project)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(f"Project assets valid: {report['panel_count']} panel(s)")
        return 0

    if args.command == "validate-fit":
        try:
            report = validate_fit(args.project)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError, FitValidationError) as exc:
            print(f"Fit validation failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "audit-regeneration":
        try:
            report = audit_regeneration(
                args.project,
                against=args.against,
                require_new_panels=args.require_new_panels,
            )
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError, RegenerationAuditError) as exc:
            print(f"Regeneration audit failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "validate-story":
        try:
            report = validate_story_gate(args.project)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError, StoryGateError) as exc:
            print(f"Story gate failed: {exc}", file=sys.stderr)
            return 1
        print(f"Story gate valid: {report['deterministic_gate']['scene_count']} scene(s), {report['deterministic_gate']['panel_count']} panel(s)")
        return 0

    if args.command == "record-story-review":
        from .review_record import record_story_review

        try:
            report = record_story_review(
                args.project,
                author_pass_id=args.author_pass_id,
                reviewer_pass_id=args.reviewer_pass_id,
                reviewer_kind=args.reviewer_kind,
                evidence_file=args.evidence_file,
                status=args.status,
                notes=args.notes,
            )
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"record-story-review failed: {exc}", file=sys.stderr)
            return 1
        gate = report.get("deterministic_gate", {}) if isinstance(report, dict) else {}
        print(
            f"Story review recorded ({args.status}). Deterministic gate passed={gate.get('passed')} "
            f"with {len(gate.get('issues', []))} issue(s); see qa/story-gate-report.json."
        )
        return 0

    if args.command == "record-appeal-review":
        from .review_record import record_appeal_review

        try:
            report = record_appeal_review(
                args.project,
                reviewer_pass_id=args.reviewer_pass_id,
                reviewer_kind=args.reviewer_kind,
                checks_file=args.checks_file,
                notes=args.notes,
            )
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"record-appeal-review failed: {exc}", file=sys.stderr)
            return 1
        print(
            f"Appeal review recorded. Validation passed={report.get('passed')} "
            f"with {len(report.get('issues', []))} issue(s); see qa/appeal-report.json."
        )
        return 0

    if args.command == "validate-argument-map":
        try:
            report = validate_argument_map(args.project)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError, ArgumentMapError) as exc:
            print(f"Argument map failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "export-argument-planning-prompt":
        try:
            result = export_argument_planning_prompt(args.project, output=args.output)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "validate-source-fidelity":
        try:
            report = validate_source_fidelity(args.project)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError, ArgumentMapError, SourceFidelityError) as exc:
            print(f"Source fidelity failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "validate-character-design":
        try:
            report = validate_character_design(args.project)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError, CharacterAgencyError) as exc:
            print(f"Character design failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "export-character-prompts":
        try:
            result = export_character_prompts(args.project, output_dir=args.output_dir)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError, CharacterAgencyError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "validate-world-specificity":
        try:
            report = validate_world_specificity(args.project, against=args.against)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError, WorldModelError, WorldSpecificityError) as exc:
            print(f"World specificity failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "export-environment-prompts":
        try:
            result = export_environment_prompts(args.project, output_dir=args.output_dir)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError, WorldModelError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "validate-conflict":
        try:
            report = validate_conflict(args.project)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError, ConflictGateError) as exc:
            print(f"Conflict gate failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "validate-page-plan":
        try:
            report = validate_page_plan(args.project)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError, PagePlanError) as exc:
            print(f"Page plan failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "validate-character-bible":
        try:
            report = validate_character_bible(args.project)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError, CharacterDesignError) as exc:
            print(f"Character bible failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "validate-environment-bible":
        try:
            report = validate_environment_bible(args.project)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError, EnvironmentDesignError) as exc:
            print(f"Environment bible failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "source-chunk":
        try:
            payload = source_chunk_project(
                args.project,
                input_path=args.input,
                chapter_id=args.chapter_id,
                max_chars=args.max_chars,
            )
        except (FileNotFoundError, OSError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(f"Wrote {len(payload['chunks'])} source chunk(s): {Path(args.project) / 'source' / 'source_chunks.json'}")
        return 0

    if args.command == "build-story-ir":
        try:
            result = build_story_ir(args.project)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "validate-source-coverage":
        try:
            report = validate_source_coverage(
                args.project,
                min_source_coverage=args.min_source_coverage,
                max_balloon_overflow_rate=args.max_balloon_overflow_rate,
            )
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Source coverage failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "validate-source-claims":
        try:
            report = validate_source_claims(args.project)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError, SourceClaimError) as exc:
            print(f"Source claims failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "validate-visual-identity":
        try:
            report = validate_visual_identity(args.project)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError, VisualIdentityError) as exc:
            print(f"Visual identity failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "validate-narrative-identity":
        try:
            report = validate_narrative_identity(args.project)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError, NarrativeIdentityError) as exc:
            print(f"Narrative identity failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "validate-distinctiveness":
        try:
            report = validate_distinctiveness(args.project, against=args.against)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError, VisualIdentityError, DistinctivenessError) as exc:
            print(f"Distinctiveness failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "build-visual-contract":
        try:
            result = build_visual_contract(args.project)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "validate-visual-contract":
        try:
            report = validate_visual_contract(args.project)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Visual contract failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "compose-project":
        try:
            result = compose_artifact_project(
                args.project,
                mode=args.mode,
                allow_gate_failures=args.allow_gate_failures,
                debug_bundle=args.debug_bundle,
            )
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        if args.allow_gate_failures:
            print("Warning: composed past failing gates; qa/delivery-gate.json records the bypass.", file=sys.stderr)
        if result.get("bundle") != "public":
            reasons = "; ".join(str(reason) for reason in result.get("rights_reasons", [])) or "debug bundle requested"
            print(
                f"Notice: bundle tier is {result.get('bundle')} — NOT for public sharing. {reasons}",
                file=sys.stderr,
            )
        modes = result.get("panel_source_modes") or []
        if any(str(mode) in {"manual-inbox", "refine-inbox"} for mode in modes):
            print(
                "Disclosure: panel artwork includes manually imported images "
                f"(source modes: {', '.join(str(mode) for mode in modes)}) — do not describe this comic as fully auto-generated.",
                file=sys.stderr,
            )
        print(json.dumps({key: str(value) for key, value in result.items()}, ensure_ascii=False, indent=2))
        # Convergence banner LAST so it is the final thing the agent reads — a
        # clean gate pass is the end of this episode's work, not an invitation
        # to re-plan and re-render a "better" version (v5.13.5 field report).
        # ASCII-only frame (no emoji / box-drawing): a check-mark emoji crashed
        # print() on a GBK Windows console and turned a SUCCESSFUL compose into
        # exit 1 (v5.13.5 smoke). The banner is a courtesy signal and must NEVER
        # be able to fail the command, so it is also wrapped defensively.
        completion = result.get("completion") or {}
        if not args.allow_gate_failures and completion.get("state") == COMPLETION_STATE_DELIVERED:
            banner = (
                "\n============================================================\n"
                "[DELIVERED / 交付完成] 本话到此为止\n"
                f"{completion.get('guidance', '')}\n"
                "============================================================"
            )
            try:
                print(banner)
            except UnicodeEncodeError:
                sys.stdout.buffer.write((banner + "\n").encode("utf-8", "replace"))
        return 0

    if args.command == "validate-delivery":
        try:
            report = validate_delivery(args.project)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Delivery validation failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "validate-grounding":
        from .grounding_qa import validate_grounding

        try:
            report = validate_grounding(args.project)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Grounding validation failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "build-cover":
        try:
            result = build_cover_assets(args.project)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Cover build failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "run-pipeline":
        try:
            result = run_pipeline(args.project, stage=args.stage, resume_panel=args.resume_panel)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Pipeline failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        # Exit codes are part of the contract: 0 all passed, 3 host action
        # required (documented, not an error), 1 any gate failed. A failed
        # pipeline exiting 0 misleads automation (release audit P0-3).
        overall = result.get("overall_status")
        if overall == "passed":
            return 0
        if overall == "host_action_required":
            print("Host action required — see steps above; exit code 3 by contract.", file=sys.stderr)
            return 3
        print("Pipeline stopped at a failed step; later stages were not run.", file=sys.stderr)
        return 1

    if args.command == "check":
        try:
            result = check_project(args.project, stage=args.stage)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Check failed: {exc}", file=sys.stderr)
            return 1
        print(f"check [{result['stage']}]: {result['passed_count']} passed, {result['failed_count']} failed")
        for item in result["checks"]:
            if item["status"] == "failed":
                print(f"  FAIL {item['check']}: {item.get('reason', '')}", file=sys.stderr)
        return 0 if result["all_passed"] else 1

    if args.command == "doctor-image-backends":
        report = probe_image_backends(
            project_dir=args.project_dir,
            codex_bin=args.codex_bin,
            run_image_selftest=args.selftest_image,
        )
        sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        return 0

    if args.command == "ensure-codex-worker":
        report = ensure_codex_cli(install=args.install, codex_bin=args.codex_bin)
        if args.selftest_image:
            from .codex_image_worker import run_codex_exec_image_selftest

            selected_bin = report.get("selected_bin")
            if selected_bin:
                report["image_selftest"] = run_codex_exec_image_selftest(codex_bin=str(selected_bin))
            else:
                report["image_selftest"] = {
                    "attempted": False,
                    "ok": False,
                    "reason": "No launchable Codex CLI was selected.",
                }
        sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        return 0

    if args.command == "extract":
        try:
            path = extract_book_to_project(args.input, args.output, force=args.force)
        except (FileNotFoundError, OSError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(f"Wrote project: {path}")
        return 0

    if args.command == "validate":
        errors = validate_project(args.project_dir)
        if errors:
            print("Project invalid:", file=sys.stderr)
            for error in errors:
                print(f"- {error}", file=sys.stderr)
            return 1
        print(f"Project valid: {args.project_dir}")
        return 0

    if args.command == "install-skill":
        try:
            destinations = install_skill(args.target, scope=args.scope, project_dir=args.project_dir)
        except (FileNotFoundError, OSError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        for destination in destinations:
            print(f"Installed book-to-comic: {destination}")
        return 0

    if args.command == "demo":
        text = render_manual_package(build_sample_package(), style_id=_resolve_style_id(args))
        _write_or_print(text, args.output)
        return 0

    if args.command == "prompt":
        if getattr(args, "prompt_mode", None) == "panel":
            try:
                text = _compile_project_panel_prompt(args.project, args.panel)
            except (FileNotFoundError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1
            _write_or_print(text, args.output)
            return 0
        if not args.book:
            parser.error("prompt requires --book, or use `prompt panel --project ... --panel ...`")
        notes = _read_notes(args.notes, args.notes_file)
        text = build_adaptation_prompt(
            book_title=args.book,
            author=args.author,
            notes=notes,
            style_id=_resolve_style_id(args),
        )
        _write_or_print(text, args.output)
        return 0

    if args.command == "export-project-prompts":
        try:
            result = export_project_prompts(args.project, episode_id=args.episode, output_dir=args.output_dir)
        except (FileNotFoundError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "export-project-text-prompts":
        try:
            result = export_project_text_prompts(args.project, episode_id=args.episode, output_dir=args.output_dir)
        except (FileNotFoundError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "validate-text-richness":
        try:
            report = validate_text_richness(args.project)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Text richness failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "validate-text-distinctiveness":
        try:
            report = validate_text_distinctiveness(args.project, against=args.against)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError, TextDistinctivenessError) as exc:
            print(f"Text distinctiveness failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "validate-lettering-fidelity":
        try:
            report = validate_lettering_fidelity(args.project)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError, LetteringFidelityError) as exc:
            print(f"Lettering fidelity failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "validate-appeal":
        try:
            report = validate_appeal(args.project)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError, AppealGateError) as exc:
            print(f"Appeal validation failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "validate-lettering-layout":
        try:
            report = validate_lettering_layout(args.project)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError, LetteringLayoutError) as exc:
            print(f"Lettering layout failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "render":
        if args.project_dir:
            try:
                paths = render_project(args.project_dir, image_backend=args.image_backend)
            except (FileNotFoundError, OSError, ValueError) as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1
            print(f"Wrote {len(paths)} {args.image_backend} panel image(s) to {Path(args.project_dir) / 'assets' / 'panels'}")
            return 0
        if not args.input:
            parser.error("render requires a project directory or --input")
        text = render_manual_package(package_from_json(args.input), style_id=_resolve_style_id(args))
        _write_or_print(text, args.output)
        return 0

    if args.command == "import-host-images":
        try:
            result = import_host_image_panels(
                args.project_dir,
                args.image_dir,
                episode_id=args.episode,
                min_width=args.min_width,
                min_height=args.min_height,
                min_file_bytes=args.min_file_bytes,
            )
        except (FileNotFoundError, OSError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(
            "Imported "
            f"{result['panel_count']} host-image panel(s) for {result['episode_id']} "
            f"to {result['panels_dir']}"
        )
        return 0

    if args.command == "prepare-host-image-batch":
        try:
            result = prepare_host_image_batch(
                args.project_dir,
                episode_id=args.episode,
                batch_dir=args.batch_dir,
                image_dir=args.image_dir,
                width=args.width,
                height=args.height,
                quality=args.quality,
            )
        except (FileNotFoundError, OSError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(
            "Prepared "
            f"{result['panel_count']} host-image job(s) for {result['episode_id']}: "
            f"{result['jobs_file']}"
        )
        print(f"Output directory: {result['image_dir']}")
        print(f"Next: generate PNGs, then run import-host-images.")
        return 0

    if args.command == "inbox-prepare":
        try:
            result = prepare_inbox(args.project_dir, episode_id=args.episode)
        except (FileNotFoundError, OSError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(f"Prepared image inbox for {result['panel_count']} panel(s): {result['inbox_dir']}")
        print("Open the README in that folder, generate each panel with any image tool (no API key),")
        print("save them as panel-01.png ... and run: book-to-comic inbox-import --project <project>")
        return 0

    if args.command == "inbox-import":
        if getattr(args, "refine", False):
            try:
                result = import_refine(
                    args.project_dir,
                    min_file_bytes=args.min_file_bytes,
                )
            except (FileNotFoundError, OSError, ValueError) as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1
            print(
                f"Imported {result['candidate_count']} refined panel(s) as CANDIDATES; originals kept in assets/refine-history/."
            )
            print(result["next_steps"])
            return 0
        try:
            result = import_inbox(
                args.project_dir,
                episode_id=args.episode,
                min_file_bytes=args.min_file_bytes,
            )
        except (FileNotFoundError, OSError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(
            f"Imported {result['panel_count']} panel image(s) as CANDIDATES for {result['episode_id']} "
            "(source_mode=manual-inbox)."
        )
        print(result["next_steps"])
        return 0

    if args.command == "refine-prepare":
        panels = None
        if args.panels:
            try:
                panels = [int(item) for item in str(args.panels).replace("，", ",").split(",") if item.strip()]
            except ValueError:
                print(f"Error: --panels must be a comma-separated list of panel numbers, got: {args.panels}", file=sys.stderr)
                return 1
        try:
            result = prepare_refine(args.project_dir, panels=panels)
        except (FileNotFoundError, OSError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(f"Prepared refine kit for {result['panel_count']} panel(s): {result['refine_dir']}")
        print("Polish each panel with any image-to-image tool (low denoise, keep composition),")
        print("save results as panel-NN.png in that folder, then run: book-to-comic inbox-import --refine --project <project>")
        return 0

    if args.command == "build-consistency-sheet":
        try:
            result = build_consistency_sheets(args.project_dir)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("Inspect every sheet in review/consistency/ before lettering and compose.", file=sys.stderr)
        return 0

    if args.command == "validate-balloon-plan":
        try:
            report = validate_project_balloon_plan(args.project)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Balloon plan validation failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if args.command == "upscale-assets":
        try:
            report = upscale_project_panels(
                args.project_dir,
                scale=args.scale,
                only_below_short_side=None if args.force else 1024,
            )
        except (FileNotFoundError, OSError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("status") != "skipped" else 1

    if args.command == "list-flat-styles":
        from .art_style import load_flat_styles

        for sid, entry in sorted(load_flat_styles().items()):
            print(f"{sid}  [{entry.get('balloon_placement','?')}]  {entry.get('display_name','')}")
        return 0

    if args.command == "set-art-style":
        from .art_style import set_flat_style

        if not args.preset and not args.style_text:
            print("Error: pass --preset <id> (built-in flat style) or --style <text> (free-form).", file=sys.stderr)
            return 1
        try:
            if args.preset:
                result = set_flat_style(args.project_dir, args.preset)
            else:
                result = set_custom_art_style(args.project_dir, args.style_text, licensed_name=args.licensed_name)
        except (FileNotFoundError, OSError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(f"Custom art style set: {result['custom_art_style'][:80]}...")
        if result.get("balloon_placement"):
            print(f"Balloon placement for this look: {result['balloon_placement']}")
        print("Applied at the top of every image prompt. Re-run export-project-prompts / inbox-prepare to refresh the prompts.")
        return 0

    if args.command == "set-card-theme":
        from .art_style import set_card_theme

        try:
            result = set_card_theme(args.project_dir, args.card_theme)
        except (FileNotFoundError, OSError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(f"Card theme set: {result['card_theme']} (uniform across the episode's cards)")
        return 0

    if args.command == "quick":
        try:
            result = quick_comic(
                args.images,
                args.captions,
                title=args.title,
                style_id=args.style,
                out_dir=args.out_dir,
            )
        except (FileNotFoundError, OSError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(f"Done — {result['panel_count']} panels composed:")
        print(f"  long image: {result['comic_long']}")
        print(f"  cards:      {result['cards_dir']} ({result['card_count']})")
        print(f"  cover:      {result['cover']}")
        print(f"  pdf:        {result['pdf']}")
        return 0

    if args.command == "generate-final":
        try:
            result = generate_final_comic(
                args.project_dir,
                backend=args.backend,
                formats=args.formats,
                codex_bin=args.codex_bin,
                width=args.width,
                height=args.height,
                quality=args.quality,
                bootstrap_codex=not args.no_bootstrap,
                image_selftest_timeout_seconds=args.image_selftest_timeout,
            )
        except (FileNotFoundError, OSError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "validate-package":
        try:
            package = package_from_json(args.input)
            errors = validate_package(package)
        except (KeyError, TypeError, ValueError, OSError) as exc:
            print(f"Package invalid: {exc}", file=sys.stderr)
            return 1
        if errors:
            print("Package invalid:", file=sys.stderr)
            for error in errors:
                print(f"- {error}", file=sys.stderr)
            return 1
        print(f"Package valid: {package.book_title} / {package.episode_title} / {len(package.storyboard)} panels")
        return 0

    if args.command == "sample-comic":
        path = render_thinking_fast_and_slow_comic(args.output, blank_text=args.blank_text)
        print(f"Wrote {path}")
        return 0

    if args.command == "compose":
        if args.project_dir:
            try:
                result = compose_project(args.project_dir)
            except (FileNotFoundError, OSError, ValueError) as exc:
                print(f"Error: {exc}", file=sys.stderr)
                return 1
            print(f"Wrote composed project assets: {result['long_image']}")
            return 0
        if args.sample:
            package = build_sample_package()
        elif args.input:
            package = package_from_json(args.input)
        else:
            parser.error("compose requires --sample or --input")
        panel_dir = args.panel_dir
        if args.source_grid:
            panel_dir = panel_dir or str(Path(args.output).with_name(Path(args.output).stem + "-panels"))
            extract_panels_from_grid(args.source_grid, panel_dir)
        path = compose_long_image(package, args.output, panel_dir=panel_dir, width=args.width, require_panels=args.require_panels)
        print(f"Wrote {path}")
        return 0

    if args.command == "export":
        try:
            results = export_project(args.project_dir, formats=args.formats)
        except (FileNotFoundError, OSError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        for name, path in results.items():
            print(f"{name}: {path}")
        return 0

    if args.command == "cards":
        if args.sample:
            package = build_sample_package()
        elif args.input:
            package = package_from_json(args.input)
        else:
            parser.error("cards requires --sample or --input")
        try:
            paths = compose_carousel_card_images(
                package,
                args.panel_dir,
                args.output_dir,
                width=args.width,
                height=args.height,
                card_theme=args.card_theme,
            )
        except (FileNotFoundError, OSError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(f"Wrote {len(paths)} carousel card images to {args.output_dir}")
        return 0

    if args.command == "export-delivery":
        try:
            path = export_cards_delivery(
                args.cards_dir,
                args.output,
                args.format,
                title=args.title,
            )
        except (FileNotFoundError, OSError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(f"Wrote {args.format} delivery: {path}")
        return 0

    if args.command == "validate-panels":
        if args.sample:
            package = build_sample_package()
        elif args.input:
            package = package_from_json(args.input)
        else:
            parser.error("validate-panels requires --sample or --input")
        try:
            report = validate_panel_images(
                args.panel_dir,
                package.storyboard,
                min_width=args.min_width,
                min_height=args.min_height,
            )
        except (FileNotFoundError, OSError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(f"Validated {len(report)} panel images in {args.panel_dir}")
        for item in report:
            print(f"{item['index']:02d}\t{item['name']}\t{item['width']}x{item['height']}")
        return 0

    if args.command == "export-panel-prompts":
        if args.sample:
            package = build_sample_package()
        elif args.input:
            package = package_from_json(args.input)
        else:
            parser.error("export-panel-prompts requires --sample or --input")
        files = export_manual_prompt_files(package, args.output_dir, style_id=_resolve_style_id(args))
        print(f"Wrote {len(files)} prompt files to {args.output_dir}")
        return 0

    if args.command == "review-package":
        if args.sample:
            package = build_sample_package()
        elif args.input:
            package = package_from_json(args.input)
        else:
            parser.error("review-package requires --sample or --input")
        try:
            result = build_review_package(
                package,
                args.panel_dir,
                args.output_dir,
                zip_path=args.zip_output,
                width=args.width,
                stem=args.stem,
            )
        except (FileNotFoundError, OSError, ValueError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print(f"Wrote review package: {result['zip']}")
        print(f"Long image: {result['long_image']}")
        print(f"Raw contact sheet: {result['raw_contact_sheet']}")
        print(f"Subtitled contact sheet: {result['subtitled_contact_sheet']}")
        return 0

    if args.command == "styles":
        if args.verbose:
            for style in iter_styles():
                print(style_show(style.id))
            return 0
        for style in iter_styles():
            print(f"{style.id}\t{style.name}\t{style.suitable_for}")
        return 0

    if args.command == "style-show":
        try:
            print(style_show(args.style_id), end="")
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        return 0

    if args.command == "style-validate":
        try:
            data = load_style_registry()
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Style registry invalid: {exc}", file=sys.stderr)
            return 1
        print(f"Style registry valid: {len(data['stable_style_ids'])} styles")
        return 0

    if args.command == "balloon-place":
        from .balloon_placer import auto_place_project

        try:
            summary = auto_place_project(args.project, force=args.force)
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Balloon placement failed: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    if args.command == "balloon-fit":
        from .balloons import estimate_balloon_box

        result = estimate_balloon_box(
            args.text,
            (args.panel_width, args.panel_height),
            "vertical" if args.vertical else "horizontal",
            purpose="webtoon" if args.webtoon else "page",
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "art-bible":
        if args.art_bible_mode != "validate":
            parser.error("art-bible requires `validate <path>`")
        try:
            data = read_art_bible(args.path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"Art bible invalid: {exc}", file=sys.stderr)
            return 1
        print(f"Art bible valid: {data['style_id']} / {data['variant_id']}")
        return 0

    parser.print_help()
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="book-to-comic",
        description="Host-native book-to-comic deterministic helpers for extraction, validation, vector rendering, composition, and delivery.",
    )
    from . import __version__ as _pkg_version

    parser.add_argument("--version", action="version", version=f"book-to-comic {_pkg_version}")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("doctor", help="Report local deterministic capabilities; does not check model API keys.")

    init = subparsers.add_parser("init-project", help="Initialize an official codex-native artifact project directory.")
    init.add_argument("--book", required=True, help="Book title.")
    init.add_argument("--project-dir", required=True, help="Output project directory.")
    init.add_argument(
        "--delivery-intent",
        default="hardcore_showcase",
        choices=("mass_traffic", "hardcore_showcase"),
        help="Publishing intent used by fit and appeal gates.",
    )
    init.add_argument("--episode-id", default="EP01", help="Episode id this project holds (one project = one episode).")
    init.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing project (files are backed up to backup/init-<timestamp>/ first). Default: refuse.",
    )

    init_series_parser = subparsers.add_parser(
        "init-series",
        help="Create a series ledger (series.json): the beat-account plan of episodes for one book. One episode = one project directory.",
    )
    init_series_parser.add_argument("--dir", required=True, help="Series directory that will hold series.json (episode projects usually live under it).")
    init_series_parser.add_argument("--book", required=True, help="Book title.")
    init_series_parser.add_argument(
        "--episodes",
        default="",
        help="Planned episodes as 'EP01:标题,EP02:标题,...' (EP01 is added automatically if omitted).",
    )

    ingest_parser = subparsers.add_parser(
        "ingest-source",
        help="Non-destructively import the book text (TXT/MD/DOCX/PDF) into a series root or an existing project. Writes ONLY source/raw_text.txt + ingest manifest; never overwrites existing source text.",
    )
    ingest_target = ingest_parser.add_mutually_exclusive_group(required=True)
    ingest_target.add_argument("--series", default=None, help="Series directory (series.json must exist; add-episode hands the text to each new episode).")
    ingest_target.add_argument("--project", default=None, help="Existing project directory (project.json must exist).")
    ingest_parser.add_argument("input", help="Book file to import (.txt/.md/.docx/.pdf).")

    add_episode_parser = subparsers.add_parser(
        "add-episode",
        help="Scaffold the next episode as its OWN project directory, carrying the series planning bibles forward. No gate shortcuts.",
    )
    add_episode_parser.add_argument("--series", required=True, help="Series directory containing series.json.")
    add_episode_parser.add_argument("--episode", required=True, help="Episode id to create, for example EP02.")
    add_episode_parser.add_argument("--project-dir", default=None, help="Project directory for this episode (default: <series>/<episode-id>/).")
    add_episode_parser.add_argument(
        "--copy-bibles-from",
        default=None,
        help="Project to copy planning bibles from (default: the most recent registered episode project).",
    )
    add_episode_parser.add_argument(
        "--delivery-intent",
        default="hardcore_showcase",
        choices=("mass_traffic", "hardcore_showcase"),
    )

    series_status_parser = subparsers.add_parser("series-status", help="Report each episode's real state, derived from its project directory.")
    series_status_parser.add_argument("--series", required=True, help="Series directory containing series.json.")

    migrate = subparsers.add_parser(
        "migrate-legacy-project",
        help="One-time migration from episodes/EP01/episode.json into official story/episode-001.json.",
    )
    migrate.add_argument("--project", required=True, help="Project directory containing the legacy episode file.")

    migrate_project_parser = subparsers.add_parser(
        "migrate-project",
        help="Migrate an existing project to schema 3.0 without inventing missing host planning.",
    )
    migrate_project_parser.add_argument("--project", required=True, help="Project directory.")
    migrate_project_parser.add_argument("--to-version", default="3.0", help="Target schema version. Only 3.0 is supported.")

    snapshot = subparsers.add_parser("snapshot-images", help="Snapshot host generated-images directories before one image generation call.")
    snapshot.add_argument("--output", required=True, help="Snapshot JSON path.")

    recover_session = subparsers.add_parser(
        "recover-session-image",
        help="Recover the latest built-in Codex image_generation_call PNG from a session JSONL file.",
    )
    recover_session.add_argument("--session", required=True, help="Codex session JSONL path.")
    recover_session.add_argument("--output", required=True, help="Workspace PNG path to write.")

    materialize = subparsers.add_parser("materialize-image", help="Normalize one host-generated image into assets/candidates and manifest.json.")
    materialize.add_argument("--project", required=True, help="Artifact project directory.")
    materialize.add_argument("--kind", required=True, choices=("character-reference", "panel"))
    materialize.add_argument("--asset-id", required=True)
    materialize.add_argument("--version", required=True, type=int)
    materialize.add_argument("--snapshot", required=True)
    materialize.add_argument("--prompt", required=True)
    materialize.add_argument("--panel-index", type=int)
    materialize.add_argument("--reference-asset", action="append")
    materialize.add_argument("--source", help="Explicit local source image path returned by the host image tool.")

    approve = subparsers.add_parser("approve-asset", help="Approve a materialized candidate into its canonical asset path.")
    approve.add_argument("--project", required=True)
    approve.add_argument("--asset-id", required=True)
    approve.add_argument("--qa-summary", required=True)

    reject = subparsers.add_parser("reject-asset", help="Reject a materialized candidate and record QA reason.")
    reject.add_argument("--project", required=True)
    reject.add_argument("--asset-id", required=True)
    reject.add_argument("--qa-summary", required=True)

    validate_assets = subparsers.add_parser("validate-project-assets", help="Validate approved canonical assets before composition.")
    validate_assets.add_argument("--project", required=True)

    validate_fit_parser = subparsers.add_parser("validate-fit", help="Validate book/topic temperature against delivery_intent before adaptation.")
    validate_fit_parser.add_argument("--project", required=True, help="Artifact project directory.")

    audit_regeneration_parser = subparsers.add_parser(
        "audit-regeneration",
        help="Compare a project against a baseline and report whether panels were truly regenerated.",
    )
    audit_regeneration_parser.add_argument("--project", required=True, help="Current artifact project directory.")
    audit_regeneration_parser.add_argument("--against", required=True, help="Baseline project directory to compare against.")
    audit_regeneration_parser.add_argument(
        "--require-new-panels",
        action="store_true",
        help="Fail unless all comparable approved panel images differ from the baseline.",
    )

    validate_story = subparsers.add_parser("validate-story", help="Validate narrative scene structure and deterministic story gates.")
    validate_story.add_argument("--project", required=True)

    record_story = subparsers.add_parser(
        "record-story-review",
        help="Record the independent story review verdict (the ONLY legal write path for llm_gate; hand-editing qa reports is forbidden).",
    )
    record_story.add_argument("--project", required=True)
    record_story.add_argument("--author-pass-id", required=True, help="Pass id of the writing pass that produced the episode.")
    record_story.add_argument("--reviewer-pass-id", required=True, help="Pass id of the independent reviewer; must differ from the author pass.")
    record_story.add_argument(
        "--reviewer-kind",
        required=True,
        choices=["independent-subagent", "separate-session", "human"],
        help="Who performed the review. Recursive full-agent providers stay forbidden; independent review passes are not recursion.",
    )
    record_story.add_argument("--evidence-file", required=True, help="JSON file with the review checks (source_excerpt -> final_text -> verdict evidence).")
    record_story.add_argument("--status", default="approved", choices=["approved", "rejected"])
    record_story.add_argument("--notes", default="", help="Optional review scope/context note stored in provenance.")

    record_appeal = subparsers.add_parser(
        "record-appeal-review",
        help="Record the appeal (感染力) review verdict (the ONLY legal write path for qa/appeal-report.json).",
    )
    record_appeal.add_argument("--project", required=True)
    record_appeal.add_argument("--reviewer-pass-id", required=True)
    record_appeal.add_argument(
        "--reviewer-kind",
        required=True,
        choices=["independent-subagent", "separate-session", "human"],
    )
    record_appeal.add_argument("--checks-file", required=True, help="JSON file with the five appeal checks and their evidence.")
    record_appeal.add_argument("--notes", default="", help="Optional review scope/context note stored in provenance.")

    validate_argument_map_parser = subparsers.add_parser(
        "validate-argument-map",
        help="Validate v3 argument map, selected arguments, source refs, and host approvals.",
    )
    validate_argument_map_parser.add_argument("--project", required=True)

    export_argument_prompt_parser = subparsers.add_parser(
        "export-argument-planning-prompt",
        help="Export a host planning prompt for planning/argument_map.json.",
    )
    export_argument_prompt_parser.add_argument("--project", required=True)
    export_argument_prompt_parser.add_argument("--output", help="Output Markdown path. Defaults to project/prompts/planning/argument-map.md.")

    validate_source_fidelity_parser = subparsers.add_parser(
        "validate-source-fidelity",
        help="Validate selected argument coverage, source chunk references, and simplification notes.",
    )
    validate_source_fidelity_parser.add_argument("--project", required=True)

    validate_character_design_parser = subparsers.add_parser(
        "validate-character-design",
        help="Validate v3 character agency, cast model, visual distinction, and active decisions.",
    )
    validate_character_design_parser.add_argument("--project", required=True)

    export_character_prompts_parser = subparsers.add_parser(
        "export-character-prompts",
        help="Export no-text character reference prompts from planning/character_bible.json.",
    )
    export_character_prompts_parser.add_argument("--project", required=True)
    export_character_prompts_parser.add_argument("--output-dir", help="Output directory. Defaults to project/prompts/characters.")

    validate_world_specificity_parser = subparsers.add_parser(
        "validate-world-specificity",
        help="Validate v3 world model specificity, institutional traces, and generic fallback density.",
    )
    validate_world_specificity_parser.add_argument("--project", required=True)
    validate_world_specificity_parser.add_argument("--against", action="append", help="Baseline project directory for optional world signature comparison.")

    export_environment_prompts_parser = subparsers.add_parser(
        "export-environment-prompts",
        help="Export no-text environment reference prompts from planning/world_model.json.",
    )
    export_environment_prompts_parser.add_argument("--project", required=True)
    export_environment_prompts_parser.add_argument("--output-dir", help="Output directory. Defaults to project/prompts/environments.")

    validate_conflict_parser = subparsers.add_parser(
        "validate-conflict",
        help="Validate visible conflict, character initiative, cause/effect, and stakes curve.",
    )
    validate_conflict_parser.add_argument("--project", required=True)

    validate_page_plan_parser = subparsers.add_parser(
        "validate-page-plan",
        help="Validate v3 comic pages, panel assignment, rhythm roles, and lettering anchors.",
    )
    validate_page_plan_parser.add_argument("--project", required=True)

    validate_character = subparsers.add_parser("validate-character-bible", help="Validate character appeal, distinction, performance, and dramatic function locks.")
    validate_character.add_argument("--project", required=True)

    validate_environment = subparsers.add_parser("validate-environment-bible", help="Validate environment bible readiness, grounding modes, anchors, materials, and location function.")
    validate_environment.add_argument("--project", required=True)

    source_chunk = subparsers.add_parser("source-chunk", help="Split source/raw_text.txt into auditable source chunks.")
    source_chunk.add_argument("--project", required=True, help="Artifact project directory.")
    source_chunk.add_argument("--input", help="Optional source text file. Defaults to <project>/source/raw_text.txt.")
    source_chunk.add_argument("--chapter-id", default="CH1", help="Chapter id prefix for generated chunks.")
    source_chunk.add_argument("--max-chars", type=int, default=1400, help="Maximum rough characters per chunk.")

    build_ir = subparsers.add_parser("build-story-ir", help="Build story_ir and drawable panel contracts from source chunks and scenes.")
    build_ir.add_argument("--project", required=True, help="Artifact project directory.")

    validate_coverage = subparsers.add_parser("validate-source-coverage", help="Validate source coverage, drawable panel contracts, balloon budget, and reading order.")
    validate_coverage.add_argument("--project", required=True, help="Artifact project directory.")
    validate_coverage.add_argument("--min-source-coverage", type=float, default=0.9)
    validate_coverage.add_argument("--max-balloon-overflow-rate", type=float, default=0.01)

    validate_claims = subparsers.add_parser("validate-source-claims", help="Validate concept units, source claim support, grounding, and semantic anchors.")
    validate_claims.add_argument("--project", required=True, help="Artifact project directory.")

    validate_visual_identity_parser = subparsers.add_parser(
        "validate-visual-identity",
        help="Validate book-specific visual identity before prompt or image generation.",
    )
    validate_visual_identity_parser.add_argument("--project", required=True, help="Artifact project directory.")

    validate_narrative_identity_parser = subparsers.add_parser(
        "validate-narrative-identity",
        help="Validate book-specific zh-CN narrative voice, lettering policy, and forbidden reusable copy.",
    )
    validate_narrative_identity_parser.add_argument("--project", required=True, help="Artifact project directory.")

    validate_distinctiveness_parser = subparsers.add_parser(
        "validate-distinctiveness",
        help="Validate local JSON-only cross-project visual distinctiveness.",
    )
    validate_distinctiveness_parser.add_argument("--project", required=True, help="Current artifact project directory.")
    validate_distinctiveness_parser.add_argument(
        "--against",
        action="append",
        help="Previous project directory to compare against. Repeat for multiple baselines.",
    )

    build_visual = subparsers.add_parser("build-visual-contract", help="Build character, environment, prop state and reference pack locks.")
    build_visual.add_argument("--project", required=True, help="Artifact project directory.")

    validate_visual = subparsers.add_parser("validate-visual-contract", help="Validate visual state locks before image generation.")
    validate_visual.add_argument("--project", required=True, help="Artifact project directory.")

    compose_assets = subparsers.add_parser("compose-project", help="Compose approved canonical assets into final comic deliverables.")
    compose_assets.add_argument("--project", required=True)
    compose_assets.add_argument("--mode", default="comic-page", choices=("comic-page", "long-scroll", "card", "review"), help="Delivery surface to prioritize after all gates pass.")
    compose_assets.add_argument(
        "--allow-gate-failures",
        action="store_true",
        help="Emit deliverables even when a gate fails. The bypass is recorded in qa/delivery-gate.json and validate-delivery will keep failing until the gates actually pass.",
    )
    compose_assets.add_argument(
        "--debug-bundle",
        action="store_true",
        help="Write production-debug.zip with the FULL working tree (source text, planning, prompts, review, qa) — never a public artifact. Without this flag compose writes production.zip (public, rights permitting) or production-private.zip (rights restricted), both containing finished deliverables only.",
    )

    validate_delivery_parser = subparsers.add_parser("validate-delivery", help="Verify final/ was emitted by a passing compose-project run and is not stale.")
    validate_delivery_parser.add_argument("--project", required=True, help="Artifact project directory.")

    validate_grounding_parser = subparsers.add_parser("validate-grounding", help="Verify the adaptation-constraint profile and its activated evidence contracts.")
    validate_grounding_parser.add_argument("--project", required=True, help="Artifact project directory.")

    build_cover = subparsers.add_parser("build-cover", help="Build 2-3 publish cover candidates from the approved cover source panel.")
    build_cover.add_argument("--project", required=True, help="Artifact project directory.")

    run_pipeline_parser = subparsers.add_parser("run-pipeline", help="Run deterministic director-mode stages and report host stop points.")
    run_pipeline_parser.add_argument("--project", required=True, help="Artifact project directory.")
    run_pipeline_parser.add_argument("--stage", default="all", choices=("plan", "visual", "text", "compose", "all"))
    run_pipeline_parser.add_argument("--resume-panel", type=int, help="Resume or report work from a specific rejected panel.")

    check_parser = subparsers.add_parser("check", help="Run ALL deterministic gates for a stage at once (plan/visual/text/assets/all), without stopping at the first failure. Writes qa/check-report.json. Use this instead of running validate-* one by one.")
    check_parser.add_argument("--project", required=True, help="Artifact project directory.")
    check_parser.add_argument("--stage", default="all", choices=("plan", "visual", "text", "assets", "all"))

    image_doctor = subparsers.add_parser(
        "doctor-image-backends",
        help="Probe save-capable image backends for saved-PNG diagnostics.",
    )
    image_doctor.add_argument("project_dir", nargs="?", help="Optional project directory written into the report.")
    image_doctor.add_argument("--codex-bin", help="Override Codex CLI path for codex-exec-image-worker probing.")
    image_doctor.add_argument(
        "--selftest-image",
        action="store_true",
        help="Run a live image-generation self-test; required before marking a backend final-ready.",
    )

    ensure_worker = subparsers.add_parser(
        "ensure-codex-worker",
        help="Find or install a normal launchable Codex CLI for the dedicated image worker, avoiding WindowsApps.",
    )
    ensure_worker.add_argument("--install", action="store_true", help="Install @openai/codex into the managed tools dir (env BOOK_TO_COMIC_TOOLS_DIR, default ~/.book-to-comic/tools) if no launchable CLI is found.")
    ensure_worker.add_argument("--codex-bin", help="Explicit Codex CLI path to test without installing.")
    ensure_worker.add_argument("--selftest-image", action="store_true", help="Also run the live saved-PNG image worker self-test.")

    extract = subparsers.add_parser("extract", help="Extract a local book file into a project source directory.")
    extract.add_argument("input", help="Input PDF, TXT, Markdown, or DOCX file (EPUB not supported — convert first).")
    extract.add_argument("--output", required=True, help="Output project directory.")
    extract.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing project (files are backed up to backup/extract-<timestamp>/ first). Default: refuse.",
    )

    validate_project_parser = subparsers.add_parser("validate", help="Validate a host-native comic project directory.")
    validate_project_parser.add_argument("project_dir", help="Project directory created by extract.")

    install_skill_parser = subparsers.add_parser("install-skill", help="Install the skill for Codex and/or Claude Code. Source-checkout only: run from the directory that contains SKILL.md (a wheel install does not ship SKILL.md, so this command is unavailable there).")
    install_skill_parser.add_argument("--target", choices=("codex", "claude", "both"), required=True)
    install_skill_parser.add_argument("--scope", choices=("project", "user"), default="project")
    install_skill_parser.add_argument("--project-dir", default=".", help="Project root used for project-scope installation.")

    demo = subparsers.add_parser("demo", help="Render the legacy Thinking Fast and Slow prompt-pack sample.")
    demo.add_argument("--style", default="editorial", choices=_style_choices())
    demo.add_argument("--style-seed", type=int, help="Seed used when --style random is selected.")
    demo.add_argument("--output", help="Markdown output path. Prints to stdout when omitted.")

    prompt = subparsers.add_parser("prompt", help="Build a legacy host-execution brief for any book, or compile a project panel prompt.")
    prompt.add_argument("prompt_mode", nargs="?", choices=("panel",), help="Use `panel` to compile one project panel prompt.")
    prompt.add_argument("--book", help="Book title.")
    prompt.add_argument("--author", default="", help="Book author.")
    prompt.add_argument("--notes", default="", help="Known notes, summary, or target angle.")
    prompt.add_argument("--notes-file", help="Read notes from a UTF-8 text file.")
    prompt.add_argument("--style", default="editorial", choices=_style_choices())
    prompt.add_argument("--style-seed", type=int, help="Seed used when --style random is selected.")
    prompt.add_argument("--project", help="Project directory for `prompt panel`.")
    prompt.add_argument("--panel", help="Panel id or number for `prompt panel`, for example P01 or 1.")
    prompt.add_argument("--output", help="Markdown output path. Prints to stdout when omitted.")

    project_prompts = subparsers.add_parser(
        "export-project-prompts",
        help="Export every panel prompt for a project episode into stable prompt files.",
    )
    project_prompts.add_argument("--project", required=True, help="Project directory containing story/episode-001.json.")
    project_prompts.add_argument("--episode", default=None, help="Episode id to VERIFY against the project's declared episode (mismatch errors; one project = one episode).")
    project_prompts.add_argument("--output-dir", help="Directory for panel-01.txt through panel-NN.txt. Defaults to project/prompts.")

    project_text_prompts = subparsers.add_parser(
        "export-project-text-prompts",
        help="Export zh-CN panel lettering prompts with narrative identity locks.",
    )
    project_text_prompts.add_argument("--project", required=True, help="Project directory containing story/episode-001.json.")
    project_text_prompts.add_argument("--episode", default=None, help="Episode id to VERIFY against the project's declared episode (mismatch errors; one project = one episode).")
    project_text_prompts.add_argument("--output-dir", help="Directory for panel-01.zh-CN.md through panel-NN.zh-CN.md. Defaults to project/text-prompts.")

    validate_text_richness_parser = subparsers.add_parser(
        "validate-text-richness",
        help="Validate long_form/card_form richness, coverage, and mobile copy overflow.",
    )
    validate_text_richness_parser.add_argument("--project", required=True, help="Artifact project directory.")

    validate_text_distinctiveness_parser = subparsers.add_parser(
        "validate-text-distinctiveness",
        help="Validate local JSON-only lettering distinctiveness and forbidden reusable phrases.",
    )
    validate_text_distinctiveness_parser.add_argument("--project", required=True, help="Current artifact project directory.")
    validate_text_distinctiveness_parser.add_argument(
        "--against",
        action="append",
        help="Previous project directory to compare against. Repeat for multiple baselines.",
    )

    validate_lettering_fidelity_parser = subparsers.add_parser(
        "validate-lettering-fidelity",
        help="Validate source-to-lettering negation and number fidelity with deterministic diffs.",
    )
    validate_lettering_fidelity_parser.add_argument("--project", required=True, help="Artifact project directory.")

    validate_appeal_parser = subparsers.add_parser(
        "validate-appeal",
        help="Validate host appeal soft-gate report with evidence: focus, emotion anchor, character appeal, memory sentence, scan test.",
    )
    validate_appeal_parser.add_argument("--project", required=True, help="Artifact project directory.")

    validate_lettering = subparsers.add_parser("validate-lettering-layout", help="Validate long/card lettering separation, overflow, font size, and safe-zone collisions.")
    validate_lettering.add_argument("--project", required=True, help="Artifact project directory.")

    render = subparsers.add_parser("render", help="Render project panel images, or render a legacy structured JSON package.")
    render.add_argument("project_dir", nargs="?", help="Project directory created by extract.")
    render.add_argument("--image-backend", default="auto", choices=("auto", "vector", "host-image", "local-model", "external-api"))
    render.add_argument("--input", help="UTF-8 JSON adaptation package path for legacy prompt-pack rendering.")
    render.add_argument("--style", choices=_style_choices(), help="Override the package style.")
    render.add_argument("--style-seed", type=int, help="Seed used when --style random is selected.")
    render.add_argument("--output", help="Markdown output path. Prints to stdout when omitted.")

    import_images = subparsers.add_parser(
        "import-host-images",
        help="Import accepted host-generated artwork into a project episode after Codex/Claude image generation.",
    )
    import_images.add_argument("project_dir", help="Project directory containing story/episode-001.json.")
    import_images.add_argument("--image-dir", required=True, help="Directory containing only final accepted panel images.")
    import_images.add_argument("--episode", default=None, help="Episode id to VERIFY against the project's declared episode (mismatch errors).")
    import_images.add_argument("--min-width", type=int, default=900, help="Minimum accepted source image width.")
    import_images.add_argument("--min-height", type=int, default=600, help="Minimum accepted source image height.")
    import_images.add_argument(
        "--min-file-bytes",
        type=int,
        default=100_000,
        help="Minimum source file size for high-quality host artwork. Keeps vector drafts out by default.",
    )

    prepare_batch = subparsers.add_parser(
        "prepare-host-image-batch",
        help="Write JSONL image-worker jobs for save-capable Codex/Claude host image generation.",
    )
    prepare_batch.add_argument("project_dir", help="Project directory containing story/episode-001.json.")
    prepare_batch.add_argument("--episode", default=None, help="Episode id to VERIFY against the project's declared episode (mismatch errors).")
    prepare_batch.add_argument("--batch-dir", help="Directory for jobs.jsonl, manifest, and worker instructions.")
    prepare_batch.add_argument("--image-dir", help="Directory where host image workers must save final PNG files.")
    prepare_batch.add_argument("--width", type=int, default=1536, help="Target panel image width for prompts.")
    prepare_batch.add_argument("--height", type=int, default=1024, help="Target panel image height for prompts.")
    prepare_batch.add_argument("--quality", default="high", choices=("medium", "high"), help="Requested image quality tier.")

    inbox_prepare = subparsers.add_parser(
        "inbox-prepare",
        help="Write a plain-language 'place images here' checklist to <project>/tmp/inbox/ so a user can generate panels with any tool (no API key) and drop them back in.",
    )
    inbox_prepare.add_argument("--project", dest="project_dir", required=True, help="Project directory containing story/episode-001.json.")
    inbox_prepare.add_argument("--episode", default=None, help="Episode id to VERIFY against the project's declared episode (mismatch errors).")

    inbox_import = subparsers.add_parser(
        "inbox-import",
        help="Import the panel images a user dropped into <project>/tmp/inbox/, then continue with compose-project.",
    )
    inbox_import.add_argument("--project", dest="project_dir", required=True, help="Project directory containing story/episode-001.json.")
    inbox_import.add_argument("--episode", default=None, help="Episode id to VERIFY against the project's declared episode (mismatch errors).")
    inbox_import.add_argument("--min-file-bytes", type=int, default=100_000, help="Minimum image file size in bytes. Resolution floor (short side >= 768) and the project aspect ratio are enforced automatically.")
    inbox_import.add_argument("--refine", action="store_true", help="Import refined panels from tmp/refine/ (partial import allowed; originals are backed up).")

    refine_prepare = subparsers.add_parser(
        "refine-prepare",
        help="Export approved panels + per-panel refine briefs to tmp/refine/ for external image-to-image polishing (Jimeng/Doubao/Keling, no API key).",
    )
    refine_prepare.add_argument("--project", dest="project_dir", required=True, help="Project directory with approved panels.")
    refine_prepare.add_argument("--panels", default="", help="Optional comma-separated panel numbers to refine, e.g. 1,3,5. Default: all approved panels.")

    consistency_parser = subparsers.add_parser(
        "build-consistency-sheet",
        help="Build per-character and per-scene consistency sheets from approved panels into review/consistency/ for host drift QA.",
    )
    consistency_parser.add_argument("--project", dest="project_dir", required=True, help="Project directory with approved panels.")

    balloon_parser = subparsers.add_parser(
        "validate-balloon-plan",
        help="Validate story/balloon_plan.json: coordinates in bounds, balloon text quotes approved dialogue, reading order sane.",
    )
    balloon_parser.add_argument("--project", required=True, help="Project directory containing story/balloon_plan.json.")

    upscale_parser = subparsers.add_parser(
        "upscale-assets",
        help="Upscale approved panels with a LOCAL Real-ESRGAN executable (BOOK_TO_COMIC_UPSCALER or PATH). Never downloads models.",
    )
    upscale_parser.add_argument("--project", dest="project_dir", required=True, help="Project directory with approved panels.")
    upscale_parser.add_argument("--scale", type=int, default=2, choices=(2, 3, 4), help="Upscale factor.")
    upscale_parser.add_argument("--force", action="store_true", help="Upscale every panel, even ones already above the 1024px publish target.")

    set_art_style = subparsers.add_parser(
        "set-art-style",
        help="Set a free-form custom art style for the project (e.g. 中国水墨留白 / 水彩绘本 / 美式复古印刷). Injected at the top of every image prompt; works for both Codex auto-generation and the manual inbox.",
    )
    set_art_style.add_argument("--project", dest="project_dir", required=True, help="Project directory (must already have planning/visual_identity.json).")
    set_art_style.add_argument("--style", dest="style_text", default=None, help="Free-form art-style description, any language.")
    set_art_style.add_argument("--preset", dest="preset", default=None, help="Apply a built-in flat style by id (see list-flat-styles): full high-strength prompt + balloon placement, no host base dilution.")
    set_art_style.add_argument(
        "--licensed-name",
        action="store_true",
        help="Declare that any named living artist/studio/brand in the style text is used under an authorization recorded in the grounding profile. Without this flag, keep the style described as technique (medium/line/color/face geometry) — the compiled prompt always carries a no-copying clause either way.",
    )

    subparsers.add_parser("list-flat-styles", help="List the built-in flat art styles (self-contained looks with per-style balloon placement).")

    set_card_theme_parser = subparsers.add_parser(
        "set-card-theme",
        help="Set the carousel-card background theme in project.json (REQUIRED before formal compose): editorial=现代白卡通用, gallery=文学名著画廊装裱, cinematic=视觉奇观深底.",
    )
    set_card_theme_parser.add_argument("--project", dest="project_dir", required=True, help="Project directory (must already have project.json).")
    set_card_theme_parser.add_argument("--theme", dest="card_theme", required=True, help="One of: editorial / gallery / cinematic.")

    quick_parser = subparsers.add_parser(
        "quick",
        help="No-agent path: turn a folder of images + a captions file into a finished comic (long image, cards, cover, PDF). No project, no planning, no gates — ideal when a chat AI (e.g. Doubao) wrote the storyboard and made the images.",
    )
    quick_parser.add_argument("--images", required=True, help="Folder with one image per panel (any file names; sorted naturally).")
    quick_parser.add_argument("--captions", required=True, help="Captions file: one block per panel, separated by a line of ---.")
    quick_parser.add_argument("--title", default="漫画", help="Title shown on the cover and header.")
    quick_parser.add_argument("--style", default="ink-sketch", choices=_style_choices()[1:], help="Lettering/layout style.")
    quick_parser.add_argument("--out", dest="out_dir", help="Output folder (default: alongside the images folder).")

    generate_final = subparsers.add_parser(
        "generate-final",
        help="Legacy dedicated-worker path: prepare image jobs, import panels, compose, and export final comic files.",
    )
    generate_final.add_argument("project_dir", help="Project directory containing story/episode-001.json.")
    generate_final.add_argument("--backend", default="auto", choices=("auto", "codex-exec-image-worker"))
    generate_final.add_argument("--formats", default="pdf,cbz,epub,long-image,zip", help="Comma-separated final export formats.")
    generate_final.add_argument("--codex-bin", help="Override Codex CLI path for the dedicated image worker.")
    generate_final.add_argument("--no-bootstrap", action="store_true", help="Do not try to install/use the managed Codex CLI automatically.")
    generate_final.add_argument("--width", type=int, default=1536, help="Target panel image width for prompts.")
    generate_final.add_argument("--height", type=int, default=1024, help="Target panel image height for prompts.")
    generate_final.add_argument("--quality", default="high", choices=("medium", "high"), help="Requested image quality tier.")
    generate_final.add_argument("--image-selftest-timeout", type=int, default=300, help="Seconds allowed for the live saved-PNG image self-test.")

    validate_package_parser = subparsers.add_parser("validate-package", help="Validate a structured adaptation JSON package.")
    validate_package_parser.add_argument("--input", required=True, help="UTF-8 JSON adaptation package path.")

    sample_comic = subparsers.add_parser("sample-comic", help="Render the Thinking Fast and Slow sample comic PNG.")
    sample_comic.add_argument(
        "--output",
        default="outputs/layout-drafts/thinking-fast-and-slow-layout-draft.png",
        help="PNG output path for the local layout draft.",
    )
    sample_comic.add_argument(
        "--blank-text",
        action="store_true",
        help="Render blank in-scene labels and cards for post-production overlay.",
    )

    compose = subparsers.add_parser("compose", help="Compose a host-native project, or compose a legacy final long PNG.")
    compose.add_argument("project_dir", nargs="?", help="Project directory created by extract.")
    source = compose.add_mutually_exclusive_group(required=False)
    source.add_argument("--sample", action="store_true", help="Use the built-in Thinking Fast and Slow sample package.")
    source.add_argument("--input", help="UTF-8 JSON adaptation package path.")
    compose.add_argument(
        "--panel-dir",
        help="Optional directory containing per-panel PNGs named 1.png, 01.png, panel-1.png, or panel_1.png.",
    )
    compose.add_argument(
        "--source-grid",
        help="Optional 2x4 sample-grid PNG to crop into per-panel art images before composing.",
    )
    compose.add_argument("--width", type=int, default=1080, help="Output PNG width in pixels.")
    compose.add_argument(
        "--require-panels",
        action="store_true",
        help="Fail instead of using placeholder art when any expected panel PNG is missing.",
    )
    compose.add_argument(
        "--output",
        default="outputs/final/comic-long.png",
        help="Final long PNG output path.",
    )

    export_project_parser = subparsers.add_parser("export", help="Export project comic deliverables: PDF, CBZ, EPUB, long image, and production ZIP. Add cards explicitly when needed.")
    export_project_parser.add_argument("project_dir", help="Project directory created by extract.")
    export_project_parser.add_argument("--formats", default="pdf,cbz,epub,long-image,zip", help="Comma-separated formats: pdf,cbz,epub,long-image,zip. Optional: cards.")

    cards = subparsers.add_parser("cards", help="Compose 1080x1440 single-panel carousel card PNGs.")
    cards_source = cards.add_mutually_exclusive_group(required=True)
    cards_source.add_argument("--sample", action="store_true", help="Use the built-in Thinking Fast and Slow sample package.")
    cards_source.add_argument("--input", help="UTF-8 JSON adaptation package path.")
    cards.add_argument("--panel-dir", required=True, help="Directory containing accepted panel PNGs.")
    cards.add_argument(
        "--output-dir",
        default="outputs/final/cards",
        help="Directory for generated 01.png through NN.png carousel cards.",
    )
    cards.add_argument("--width", type=int, default=1080, help="Card width in pixels.")
    cards.add_argument("--height", type=int, default=1440, help="Card height in pixels.")
    cards.add_argument("--card-theme", choices=("editorial", "gallery", "cinematic"), default=None, help="Background theme: editorial (default/general), gallery (literary), cinematic (spectacle).")

    delivery = subparsers.add_parser("export-delivery", help="Export a user-facing PDF, CBZ, or production ZIP from ordered card PNGs.")
    delivery.add_argument("--cards-dir", required=True, help="Directory containing ordered PNG cards such as 01.png, 02.png.")
    delivery.add_argument("--format", required=True, choices=DELIVERY_FORMATS, help="Delivery format to write.")
    delivery.add_argument("--output", required=True, help="Output path, for example comic.pdf, comic.cbz, or comic-production.zip.")
    delivery.add_argument("--title", default="comic", help="Title written into production ZIP manifest.")

    validate = subparsers.add_parser("validate-panels", help="Validate a complete directory of accepted panel PNGs.")
    validate_source = validate.add_mutually_exclusive_group(required=True)
    validate_source.add_argument("--sample", action="store_true", help="Use the built-in Thinking Fast and Slow sample package.")
    validate_source.add_argument("--input", help="UTF-8 JSON adaptation package path.")
    validate.add_argument("--panel-dir", required=True, help="Directory containing accepted panel PNGs.")
    validate.add_argument("--min-width", type=int, default=512, help="Minimum accepted panel width in pixels.")
    validate.add_argument("--min-height", type=int, default=256, help="Minimum accepted panel height in pixels.")

    export_prompts = subparsers.add_parser("export-panel-prompts", help="Write character and per-panel legacy prompt files.")
    export_source = export_prompts.add_mutually_exclusive_group(required=True)
    export_source.add_argument("--sample", action="store_true", help="Use the built-in Thinking Fast and Slow sample package.")
    export_source.add_argument("--input", help="UTF-8 JSON adaptation package path.")
    export_prompts.add_argument("--style", default="franco-belgian-bd", choices=_style_choices())
    export_prompts.add_argument("--style-seed", type=int, help="Seed used when --style random is selected.")
    export_prompts.add_argument(
        "--output-dir",
        default="outputs/panel-prompts/thinking-fast-and-slow-bd",
        help="Directory for prompt txt files.",
    )

    review = subparsers.add_parser("review-package", help="Build a review package from accepted panel PNGs.")
    review_source = review.add_mutually_exclusive_group(required=True)
    review_source.add_argument("--sample", action="store_true", help="Use the built-in Thinking Fast and Slow sample package.")
    review_source.add_argument("--input", help="UTF-8 JSON adaptation package path.")
    review.add_argument("--panel-dir", required=True, help="Directory containing accepted panel PNGs.")
    review.add_argument(
        "--output-dir",
        default="outputs/claude-review",
        help="Directory for contact sheets, subtitled panels, long image, manifest, and zip.",
    )
    review.add_argument("--zip-output", help="Optional explicit zip output path.")
    review.add_argument("--width", type=int, default=1080, help="Review long image and subtitled panel width.")
    review.add_argument("--stem", help="Filename stem for generated review artifacts.")

    styles = subparsers.add_parser("styles", help="List built-in style IDs.")
    styles.add_argument("--verbose", action="store_true", help="Show production name, variants, core signatures, and hard failures.")
    style_show_parser = subparsers.add_parser("style-show", help="Show one style preset in verbose form.")
    style_show_parser.add_argument("style_id", choices=_style_choices()[1:])
    subparsers.add_parser("style-validate", help="Validate the bundled structured style registry.")

    balloon_place = subparsers.add_parser("balloon-place", help="Auto-place missing balloon boxes from anchors + no_go_boxes (deterministic; VLM marks regions, geometry picks coordinates).")
    balloon_place.add_argument("--project", required=True, help="Artifact project directory.")
    balloon_place.add_argument("--force", action="store_true", help="Re-place every balloon, replacing existing boxes.")

    balloon_fit = subparsers.add_parser("balloon-fit", help="Estimate a normalized balloon box size for a dialogue line before placing it.")
    balloon_fit.add_argument("--text", required=True, help="Dialogue line (speaker prefix is stripped).")
    balloon_fit.add_argument("--panel-width", type=int, required=True)
    balloon_fit.add_argument("--panel-height", type=int, required=True)
    balloon_fit.add_argument("--vertical", action="store_true", help="Vertical CJK writing mode.")
    balloon_fit.add_argument("--webtoon", action="store_true", help="Mobile-first webtoon sizing (larger em).")
    art_bible = subparsers.add_parser("art-bible", help="Art Direction Bible helpers.")
    art_bible.add_argument("art_bible_mode", choices=("validate",))
    art_bible.add_argument("path")
    return parser


def _style_choices() -> tuple[str, ...]:
    return ("random",) + list_style_ids()


def _resolve_style_id(args: argparse.Namespace) -> str | None:
    style = getattr(args, "style", None)
    if style == "random":
        return choose_random_style(seed=getattr(args, "style_seed", None)).id
    return style


def _read_notes(notes: str, notes_file: str | None) -> str:
    if notes_file:
        file_text = Path(notes_file).read_text(encoding="utf-8")
        if notes:
            return notes.rstrip() + "\n\n" + file_text.strip()
        return file_text.strip()
    return notes


def _write_or_print(text: str, output: str | None) -> None:
    if not output:
        sys.stdout.write(text)
        return

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(text, encoding="utf-8")
    print(f"Wrote {output_path}")


def _compile_project_panel_prompt(project_dir: str | None, panel_ref: str | None) -> str:
    if not project_dir:
        raise ValueError("--project is required for prompt panel")
    if not panel_ref:
        raise ValueError("--panel is required for prompt panel")
    root = Path(project_dir)
    episode = load_episode(root)
    default_aspect = project_panel_aspect_ratio(root)
    panel = _find_panel(_episode_panels(episode), panel_ref)
    style = get_style(str(episode.get("style_id", "editorial")))
    characters = _project_characters(root)
    environments = _project_environments(root)
    props = _project_props(panel)
    reference_pack = _project_reference_pack(root)
    visual_identity = _project_visual_identity(root)
    spec = PanelArtSpec(
        panel_id=str(panel.get("panel_id", "")),
        characters_present=tuple(str(item) for item in panel.get("characters_present", ())),
        environment_id=str(panel.get("setting", panel.get("environment_id", ""))),
        time=str(panel.get("time", "")),
        shot_size=str(panel.get("shot_size", "medium")),
        camera_angle=str(panel.get("camera_angle", "eye-level")),
        lens_feel=str(panel.get("lens_feel", "natural")),
        focal_point=str(panel.get("focal_point", panel.get("visual", ""))),
        foreground=str(panel.get("foreground", "")),
        midground=str(panel.get("midground", "")),
        background=str(panel.get("background", "")),
        action=str(panel.get("action", panel.get("visual", ""))),
        emotion=str(panel.get("emotion", "")),
        eyeline=str(panel.get("eyeline", "")),
        props_and_states=_panel_props_and_states(panel),
        continuity_from=str(panel.get("continuity_from", "")),
        transition_to_next=str(panel.get("transition_to_next", "")),
        lettering_safe_zone=", ".join(str(item) for item in panel.get("caption_safe_zones", ())) or "natural negative space",
        aspect_ratio=str(panel.get("aspect_ratio") or default_aspect),
    )
    return compile_panel_prompt(
        style,
        spec,
        characters=characters,
        environments=environments,
        props=props,
        reference_pack=reference_pack,
        visual_identity=visual_identity,
    )


def _episode_panels(episode: dict[str, object]) -> list[object]:
    panels = episode.get("panels")
    if isinstance(panels, list) and panels:
        return panels
    scenes = episode.get("scenes")
    if not isinstance(scenes, list):
        return []
    result: list[object] = []
    for scene in scenes:
        if isinstance(scene, dict) and isinstance(scene.get("panels"), list):
            result.extend(scene["panels"])
    return result


def _find_panel(panels: object, panel_ref: str) -> dict[str, object]:
    if not isinstance(panels, list):
        raise ValueError("episode panels must be a list")
    normalized = panel_ref.upper()
    if panel_ref.isdigit():
        normalized = f"P{int(panel_ref):02d}"
    for panel in panels:
        if isinstance(panel, dict) and str(panel.get("panel_id", "")).upper() == normalized:
            return panel
    raise ValueError(f"Panel not found: {panel_ref}")


def _project_characters(root: Path) -> dict[str, str]:
    path = root / "planning" / "character_bible.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    characters: dict[str, str] = {}
    for item in data.get("characters", []):
        if not isinstance(item, dict):
            continue
        value = item.get("prompt_fragment") or item.get("visual") or item.get("name")
        if value:
            if item.get("id"):
                characters[str(item["id"])] = str(value)
            if item.get("name"):
                characters[str(item["name"])] = str(value)
    return characters


def _project_environments(root: Path) -> dict[str, str]:
    path = root / "planning" / "environment_bible.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    environments: dict[str, str] = {}
    for item in data.get("environments", []):
        if not isinstance(item, dict):
            continue
        anchors = ", ".join(str(anchor) for anchor in item.get("anchors", []))
        environments[str(item.get("id", item.get("name", "")))] = f"{item.get('name', '')}; anchors: {anchors}".strip()
    return environments


def _project_props(panel: dict[str, object]) -> dict[str, str]:
    props: dict[str, str] = {}
    for item in panel.get("props", ()):
        props[str(item)] = str(item)
    return props


def _panel_props_and_states(panel: dict[str, object]) -> dict[str, str]:
    value = panel.get("props_and_states")
    if isinstance(value, dict):
        return {str(key): str(item) for key, item in value.items()}
    return {str(item): str(item) for item in panel.get("props", ())}


def _project_reference_pack(root: Path) -> dict[str, object]:
    reference_path = root / "review" / "reference-pack.json"
    if reference_path.exists():
        return json.loads(reference_path.read_text(encoding="utf-8"))
    contract_path = root / "planning" / "visual_contract.json"
    if contract_path.exists():
        data = json.loads(contract_path.read_text(encoding="utf-8"))
        reference_pack = data.get("reference_pack", {})
        if isinstance(reference_pack, dict):
            return reference_pack
    return {}


def _project_visual_identity(root: Path) -> dict[str, object]:
    path = root / "planning" / "visual_identity.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}
