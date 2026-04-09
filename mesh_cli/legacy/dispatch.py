from __future__ import annotations

import argparse
import sys
from types import ModuleType
from typing import Any, cast

from ..version_info import get_tool_version
from .registry import register_commands


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mesh Engine CLI")
    parser.add_argument("--version", action="store_true", help="Show engine version")
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to run")
    register_commands(subparsers)
    return parser


def create_parser() -> argparse.ArgumentParser:
    return build_parser()


def dispatch(
    args: argparse.Namespace,
    *,
    parser: argparse.ArgumentParser | None = None,
    impl_module: ModuleType | None = None,
) -> int:
    impl_candidate = impl_module
    if impl_candidate is None:
        from .. import legacy_impl as impl_candidate  # pragma: no cover - compatibility path
    impl = cast(Any, impl_candidate)

    if getattr(args, "version", False):
        print(f"Mesh Engine {get_tool_version()}")
        return 0

    if not getattr(args, "command", None):
        if parser is None:
            parser = build_parser()
        parser.print_help()
        return 1

    if args.command == "play":
        return int(impl._handle_play(args))
    if args.command == "demo":
        if getattr(args, "demo_command", None) in (None, "", "run"):
            return int(impl._handle_demo(args))
        if getattr(args, "demo_command", None) == "scaffold-objective":
            return int(impl._handle_demo_scaffold_objective(args))
        if getattr(args, "demo_command", None) == "pipeline":
            from .. import demo as demo_pipeline

            return int(demo_pipeline.handle(args))
        print("[Mesh][CLI] Error: missing demo subcommand")
        return 2
    if args.command == "validate":
        from .. import scene as scene_commands

        return int(scene_commands.handle(args))
    if args.command == "index":
        return int(impl._handle_index(args))
    if args.command == "docs":
        return int(impl._handle_docs(args))
    if args.command == "wizard":
        return int(impl._handle_wizard(args))
    if args.command == "new-scene":
        from .. import scene as scene_commands

        return int(scene_commands.handle(args))
    if args.command == "new-behaviour":
        return int(impl._handle_new_behaviour(args))
    if args.command == "selftest":
        return int(impl._handle_selftest(args))
    if args.command == "ai-audit":
        from .. import ai as ai_commands
        return int(ai_commands.handle(args))
    if args.command == "tidy-scene":
        from .. import scene as scene_commands

        return int(scene_commands.handle(args))
    if args.command == "scene":
        from .. import scene as scene_commands

        return int(scene_commands.handle(args))
    if args.command == "world":
        from .. import world as world_commands

        return int(world_commands.handle(args))
    if args.command == "room":
        from .. import room as room_commands

        return int(room_commands.handle(args))
    if args.command == "tilemap":
        if getattr(args, "tilemap_command", None) == "validate":
            return int(impl._handle_tilemap_validate(args))
        print("[Mesh][CLI] Error: missing tilemap subcommand")
        return 2
    if args.command == "stamp":
        from .. import stamps as stamp_commands

        return int(stamp_commands.handle(args))

    if args.command == "brush":
        from .. import stamps as stamp_commands

        return int(stamp_commands.handle(args))

    if args.command == "macro":
        from .. import macro as macro_commands

        return int(macro_commands.handle(args))

    if args.command == "pack":
        from .. import pack as pack_commands

        return int(pack_commands.handle(args))

    if args.command == "fx":
        from .. import fx as fx_commands

        return int(fx_commands.handle(args))

    if args.command == "capture":
        from .. import stamps as stamp_commands

        return int(stamp_commands.handle(args))

    if args.command == "sprite":
        from .. import assets as asset_commands

        return int(asset_commands.handle(args))
    if args.command == "validate-world":
        from .. import world as world_commands

        return int(world_commands.handle(args))
    if args.command == "validate-events":
        from .. import qa as qa_commands

        return int(qa_commands.handle(args))
    if args.command == "validate-all":
        from .. import qa as qa_commands

        return int(qa_commands.handle(args))
    if args.command == "doctor":
        from .. import qa as qa_commands

        return int(qa_commands.handle(args))
    if args.command == "explain":
        from .. import qa as qa_commands

        return int(qa_commands.handle(args))
    if args.command == "schema-fix-ids":
        from engine.tooling import schema_fix_ids

        argv2: list[str] = []
        if getattr(args, "dry_run", False):
            argv2.append("--dry-run")
        schema_fix_paths = getattr(args, "paths", None)
        if schema_fix_paths:
            argv2.append("--paths")
            argv2.extend(list(schema_fix_paths))
        return int(schema_fix_ids.main(argv2))
    if args.command == "new-quest":
        return int(impl._handle_new_quest(args))
    if args.command == "world-graph":
        from .. import world as world_commands

        return int(world_commands.handle(args))
    if args.command == "polish":
        return int(impl._handle_polish(args))
    if args.command == "new-npc":
        return int(impl._handle_new_npc(args))
    if args.command in {"new-prefab", "place-prefab", "prefab"}:
        from .. import prefabs as prefab_commands

        return int(prefab_commands.handle(args))
    if args.command == "check":
        from .. import qa as qa_commands

        return int(qa_commands.handle(args))
    if args.command in {"verify-demo", "verify-strict", "verify-replays", "verify-all", "verify-local"}:
        from .. import verify as verify_commands

        return int(verify_commands.handle(args))
    if args.command == "list-scenes":
        from .. import scene as scene_commands

        return int(scene_commands.handle(args))
    if args.command == "list-worlds":
        return int(impl._handle_list_worlds(args))
    if args.command == "list-encounter-presets":
        return int(impl._handle_list_encounter_presets(args))
    if args.command == "lint-presets":
        return int(impl._handle_lint_presets(args))
    if args.command == "doctor-assets":
        return int(impl._handle_doctor_assets(args))
    if args.command == "assets":
        from .. import assets as asset_commands

        return int(asset_commands.handle(args))
    if args.command == "release":
        from .. import release as release_commands

        return int(release_commands.handle(args))
    if args.command == "version":
        from .. import version as version_commands

        return int(version_commands.handle(args))
    if args.command == "bundle":
        from .. import bundle_verify as bundle_verify_commands

        return int(bundle_verify_commands.handle(args))
    if args.command == "debug":
        from .. import debug as debug_commands

        return int(debug_commands.handle(args))
    if args.command == "dump-state":
        return int(impl._handle_dump_state(args))
    if args.command == "replay-script":
        from .. import replay as replay_commands

        return int(replay_commands.handle(args))

    if args.command == "replay-suite":
        from .. import replay as replay_commands

        return int(replay_commands.handle(args))
    if args.command == "replay-hash":
        from .. import replay as replay_commands

        return int(replay_commands.handle(args))
    if args.command == "demo":
        return int(impl._handle_demo(args))
    if args.command in {"pipeline", "recipes", "run-preset", "preset"}:
        from .. import pipeline as pipeline_commands

        return int(pipeline_commands.handle(args))
    if args.command == "place-npc":
        return int(impl._handle_place_npc(args))
    if args.command == "trace":
        from .. import replay as replay_commands

        return int(replay_commands.handle(args))
    if args.command in {"cutscene-simulate", "cutscene-validate"}:
        from .. import cutscene as cutscene_commands

        return int(cutscene_commands.handle(args))
    if args.command == "migrate":
        from engine.tooling import migrate_command

        return int(migrate_command.handle_migrate(args))
    if args.command in {"build-demo", "dist", "release", "pack", "cli-snapshot", "replay-goldens", "golden-slice"}:
        from .. import build as build_commands

        return int(build_commands.handle(args))
    if args.command == "apply-plan":
        from .. import ai as ai_commands
        return int(ai_commands.handle(args))
    if args.command == "undo-last-plan":
        from .. import ai as ai_commands
        return int(ai_commands.handle(args))
    if args.command == "plan":
        from .. import plan as plan_commands

        return int(plan_commands.handle(args))
    if args.command == "ai-generate-plan":
        from .. import ai as ai_commands
        return int(ai_commands.handle(args))
    if args.command == "ai-bundle":
        from .. import ai as ai_commands
        return int(ai_commands.handle(args))
    if args.command == "ai-history":
        from .. import ai as ai_commands
        return int(ai_commands.handle(args))
    if args.command == "ai-export-context":
        from .. import ai as ai_commands
        return int(ai_commands.handle(args))
    if args.command == "auto-wire-transitions":
        from .. import world as world_commands

        return int(world_commands.handle(args))
    if args.command == "cli-smoke":
        from .. import qa as qa_commands

        return int(qa_commands._handle_cli_smoke(args))
    if args.command in {"encounter-report", "drift-check"}:
        from .. import reports as report_commands

        return int(report_commands.handle(args))
    if args.command == "edit-scene":
        from .. import scene as scene_commands

        return int(scene_commands.handle(args))
    if args.command == "add-puzzle":
        return int(impl._handle_add_puzzle(args))
    if args.command == "export":
        from .. import export as export_commands

        return int(export_commands.handle(args))
    if args.command == "campaign":
        from .. import campaign as campaign_commands

        return int(campaign_commands.handle(args))
    if args.command == "new-game":
        from .. import new_game as new_game_commands

        return int(new_game_commands.handle(args))
    if args.command == "content":
        from .. import content as content_commands

        return int(content_commands.handle(args))
    if args.command == "episode":
        from .. import episode as episode_commands

        return int(episode_commands.handle(args))
    if args.command == "replays":
        from .. import replays as replays_commands

        return int(replays_commands.handle(args))
    if hasattr(args, "func"):
        result = args.func(args)
        return int(result) if isinstance(result, int) else 0

    return 1


def main(argv: list[str] | None = None, *, impl_module: ModuleType | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return dispatch(args, parser=parser, impl_module=impl_module)


if __name__ == "__main__":
    sys.exit(main())
