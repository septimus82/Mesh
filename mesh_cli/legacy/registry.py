from __future__ import annotations

import argparse
from types import SimpleNamespace
from typing import Any

_TOOLING_BINDINGS: SimpleNamespace | None = None


def load_tooling_bindings() -> SimpleNamespace:
    global _TOOLING_BINDINGS
    if _TOOLING_BINDINGS is not None:
        return _TOOLING_BINDINGS

    from engine.config import load_config
    from engine.encounter_report import generate_encounter_report
    from engine.tooling import (
        migrate_command,
        plan_linter,
        replay_script,
        replay_suite,
        state_dump,
        triage_command,
        validate_all,
        verify_demo,
    )
    from engine.tooling.content_inventory import list_scenes as _inventory_list_scenes
    from engine.tooling.content_inventory import list_worlds as _inventory_list_worlds

    _TOOLING_BINDINGS = SimpleNamespace(
        load_config=load_config,
        generate_encounter_report=generate_encounter_report,
        migrate_command=migrate_command,
        plan_linter=plan_linter,
        replay_script=replay_script,
        replay_suite=replay_suite,
        state_dump=state_dump,
        triage_command=triage_command,
        validate_all=validate_all,
        verify_demo=verify_demo,
        _inventory_list_scenes=_inventory_list_scenes,
        _inventory_list_worlds=_inventory_list_worlds,
    )
    return _TOOLING_BINDINGS


def register_commands(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    # --- Core Commands ---
    from .. import misc as misc_commands
    misc_commands.register(subparsers)

    from .. import debug as debug_commands
    debug_commands.register(subparsers)

    from .. import debug_report as debug_report_commands
    debug_report_commands.register(subparsers)

    from .. import health_report as health_report_commands
    health_report_commands.register(subparsers)

    from .. import verify_report as verify_report_commands
    verify_report_commands.register(subparsers)

    from .. import verify as verify_commands
    verify_commands.register(subparsers)

    from .. import pack as pack_commands
    pack_commands.register(subparsers)

    from .. import fx as fx_commands
    fx_commands.register(subparsers)

    from .. import release_contract as release_contract_commands
    release_contract_commands.register(subparsers)

    from .. import release as release_commands
    release_commands.register(subparsers)

    from .. import version as version_commands
    version_commands.register(subparsers)

    from .. import bundle_verify as bundle_verify_commands
    bundle_verify_commands.register(subparsers)

    from .. import artifacts_validate as artifacts_validate_commands
    artifacts_validate_commands.register(subparsers)

    from .. import artifacts_diff as artifacts_diff_commands
    artifacts_diff_commands.register(subparsers)

    from .. import baseline_update as baseline_update_commands
    baseline_update_commands.register(subparsers)

    from engine.tooling import perf_command
    perf_command.add_perf_run_command(subparsers)

    list_worlds_parser = subparsers.add_parser("list-worlds", help="List and analyze world JSON files (no engine load)")
    list_worlds_parser.add_argument("--out", help="Optional path to write JSON output")

    list_presets_parser = subparsers.add_parser(
        "list-encounter-presets", help="List available encounter preset ids (no engine load)"
    )
    list_presets_parser.add_argument("--out", help="Optional path to write JSON output")

    lint_presets_parser = subparsers.add_parser(
        "lint-presets",
        help="Check that all scene encounter_preset_id values exist (no engine load)",
    )
    lint_presets_parser.add_argument("--out", help="Optional path to write JSON output")

    # --- Content Management ---
    from .. import assets as asset_commands
    asset_commands.register(subparsers)

    from .. import authoring as authoring_commands
    authoring_commands.register(subparsers)

    from .. import scene as scene_commands
    scene_commands.register(subparsers)

    from .. import world as world_commands
    world_commands.register(subparsers)

    from .. import room as room_commands
    room_commands.register(subparsers)

    tilemap_parser = subparsers.add_parser("tilemap", help="Tilemap utilities")
    tilemap_subparsers = tilemap_parser.add_subparsers(dest="tilemap_command", help="Tilemap subcommand")
    tilemap_validate_parser = tilemap_subparsers.add_parser(
        "validate",
        help="Validate tilemap multi-layer configuration in a scene",
    )
    tilemap_validate_parser.add_argument("scene_path", help="Path to scene file")

    from .. import macro as macro_commands
    macro_commands.register(subparsers)

    # --- Validation ---
    from .. import qa as qa_commands
    qa_commands.register(subparsers)

    subparsers.add_parser("selftest", help="Run engine self-tests")

    from .. import pipeline as pipeline_commands
    pipeline_commands.register(subparsers)

    load_tooling_bindings().triage_command.add_triage_command(subparsers)

    from engine.tooling import assist_command
    assist_command.add_assist_command(subparsers)

    # --- Planning & AI ---
    from .. import plan as plan_commands
    plan_commands.register(subparsers)

    from .. import ai as ai_commands
    ai_commands.register(subparsers)

    from .. import reports as report_commands
    report_commands.register(subparsers)

    from .. import stamps as stamp_commands
    stamp_commands.register(subparsers)

    from .. import prefabs as prefab_commands
    prefab_commands.register(subparsers)

    # --- Tooling Modules ---
    from .. import replay as replay_commands
    replay_commands.register(subparsers)

    from .. import cutscene as cutscene_commands
    cutscene_commands.register(subparsers)

    from .. import build as build_commands
    build_commands.register(subparsers)

    from .. import export as export_commands
    export_commands.register(subparsers)

    from .. import campaign as campaign_commands
    campaign_commands.register(subparsers)

    from .. import new_game as new_game_commands
    new_game_commands.register(subparsers)

    from .. import content as content_commands
    content_commands.register(subparsers)

    from .. import episode as episode_commands
    episode_commands.register(subparsers)

    from .. import replays as replays_commands
    replays_commands.register(subparsers)


TOOLING_EXPORT_NAMES: tuple[str, ...] = (
    "load_config",
    "generate_encounter_report",
    "migrate_command",
    "plan_linter",
    "replay_script",
    "replay_suite",
    "state_dump",
    "triage_command",
    "validate_all",
    "verify_demo",
    "_inventory_list_scenes",
    "_inventory_list_worlds",
)


def get_tooling_export(name: str) -> Any:
    bindings = load_tooling_bindings()
    return getattr(bindings, name)
