"""Core and Misc commands."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from engine.config import load_config
from engine.persistence_io import write_json_atomic, dumps_json_deterministic
from engine.logging_tools import suppress_stdout
from engine.tooling import wizard_command, state_dump
from mesh_cli import scene as scene_commands

def handle(args: argparse.Namespace) -> int:
    if args.command == "play":
        return _handle_play(args)
    if args.command == "demo":
        if getattr(args, "demo_command", None) in (None, "", "run"):
            return _handle_demo(args)
        if getattr(args, "demo_command", None) == "scaffold-objective":
            return _handle_demo_scaffold_objective(args)
        print("[Mesh][CLI] Error: missing demo subcommand")
        return 2
    if args.command == "wizard":
        return _handle_wizard(args)
    if args.command == "docs":
        return _handle_docs(args)
    if args.command == "dump-state":
        return _handle_dump_state(args)
    return 1

def register(subparsers: argparse._SubParsersAction) -> None:
    # Play
    play_parser = subparsers.add_parser("play", help="Launch the game")
    play_parser.add_argument("scene_path", nargs="?", help="Optional start scene")

    # Demo
    demo_parser = subparsers.add_parser("demo", help="Demo helpers")
    demo_subparsers = demo_parser.add_subparsers(dest="demo_command", help="Demo subcommand")

    demo_run_parser = demo_subparsers.add_parser("run", help="Launch the Mesh Showcase demo")
    demo_run_parser.add_argument("--scene", dest="scene_override", help="Override start scene path")
    # Also add --scene to the base demo parser for `mesh demo --scene`
    demo_parser.add_argument("--scene", dest="scene_override", help="Override start scene path")

    scaffold_obj = demo_subparsers.add_parser(
        "scaffold-objective",
        help="Scaffold a 3-beat objective (dialogue start + interior + cellar triggers)",
    )
    scaffold_obj.add_argument("--start-scene", required=True, help="Start scene path (dialogue speaker lives here)")
    scaffold_obj.add_argument("--speaker-id", required=True, help="Speaker entity id in start scene")
    scaffold_obj.add_argument("--choice-id", required=True, help="Dialogue choice id")
    scaffold_obj.add_argument("--choice-text", required=True, help="Dialogue choice text")

    scaffold_obj.add_argument("--interior-scene", required=True, help="Interior scene path")
    scaffold_obj.add_argument("--interior-x", type=float, required=True, help="Interior trigger X")
    scaffold_obj.add_argument("--interior-y", type=float, required=True, help="Interior trigger Y")
    scaffold_obj.add_argument("--interior-radius", type=float, required=True, help="Interior trigger radius")

    scaffold_obj.add_argument("--cellar-scene", required=True, help="Cellar scene path")
    scaffold_obj.add_argument("--cellar-x", type=float, required=True, help="Cellar trigger X")
    scaffold_obj.add_argument("--cellar-y", type=float, required=True, help="Cellar trigger Y")
    scaffold_obj.add_argument("--cellar-radius", type=float, required=True, help="Cellar trigger radius")

    scaffold_obj.add_argument("--flag-started", required=True, dest="flag_started", help="Objective started flag")
    scaffold_obj.add_argument("--flag-mid", required=True, dest="flag_mid", help="Objective midpoint flag")
    scaffold_obj.add_argument("--flag-done", required=True, dest="flag_done", help="Objective done flag")

    # Demo pipeline (full orchestration)
    from . import demo as demo_pipeline  # noqa: PLC0415

    demo_pipeline.register_subcommand(demo_subparsers)

    # Wizard
    wizard_parser = subparsers.add_parser("wizard", help="Interactive content wizard")
    wizard_command.add_wizard_arguments(wizard_parser)

    # Docs
    docs_parser = subparsers.add_parser("docs", help="Generate documentation")
    docs_parser.add_argument("--verify", action="store_true", help="Verify docs are up to date")

    # Dump State
    dump_state_parser = subparsers.add_parser("dump-state", help="Print a deterministic debug state snapshot")
    dump_state_parser.add_argument("--out", help="Optional path to write JSON instead of stdout")

def _handle_play(args: argparse.Namespace) -> int:
    """Launch the game window, optionally overriding the start scene."""
    from engine.game import GameWindow

    config = load_config()
    if args.scene_path:
        config.start_scene = args.scene_path

    window = GameWindow(
        width=config.width,
        height=config.height,
        title=config.title,
        fullscreen=config.fullscreen,
        vsync=config.vsync,
        config=config,
        config_path="config.json",
    )

    # Preload the scene to catch errors early, similar to main.py
    try:
        window.load_scene(config.start_scene)
    except Exception as exc:  # noqa: BLE001
        print(f"[Mesh][CLI] Failed to load scene '{config.start_scene}': {exc}")
        return 1

    window.run()
    return 0

def _handle_demo(args: argparse.Namespace) -> int:
    """Launch the Mesh Showcase demo."""
    from engine.tooling.demo_runner import launch_demo

    scene_override = getattr(args, "scene_override", None)
    return int(launch_demo(start_scene=scene_override))

def _sanitize_entity_id_token(token: str) -> str:
    """Sanitize a string for use in an entity ID."""
    return "".join(c for c in token if c.isalnum() or c == "_")

def _handle_demo_scaffold_objective(args: argparse.Namespace) -> int:
    """Scaffold a 2–3 beat objective path across multiple scenes."""
    started_toast = "Objective: Enter the cellar"
    mid_toast = "Objective: Find the cellar"
    done_toast = "Objective complete!"

    start_scene = str(getattr(args, "start_scene", "") or "").strip()
    speaker_id = str(getattr(args, "speaker_id", "") or "").strip()
    choice_id = str(getattr(args, "choice_id", "") or "").strip()
    choice_text = str(getattr(args, "choice_text", "") or "").strip()

    interior_scene = str(getattr(args, "interior_scene", "") or "").strip()
    interior_x = float(getattr(args, "interior_x", 0.0))
    interior_y = float(getattr(args, "interior_y", 0.0))
    interior_radius = float(getattr(args, "interior_radius", 0.0))

    cellar_scene = str(getattr(args, "cellar_scene", "") or "").strip()
    cellar_x = float(getattr(args, "cellar_x", 0.0))
    cellar_y = float(getattr(args, "cellar_y", 0.0))
    cellar_radius = float(getattr(args, "cellar_radius", 0.0))

    flag_started = str(getattr(args, "flag_started", "") or "").strip()
    flag_mid = str(getattr(args, "flag_mid", "") or "").strip()
    flag_done = str(getattr(args, "flag_done", "") or "").strip()

    if not (start_scene and speaker_id and choice_id and choice_text and interior_scene and cellar_scene):
        print("[Mesh][CLI] Error: missing required scaffold arguments")
        return 2
    if not (flag_started and flag_mid and flag_done):
        print("[Mesh][CLI] Error: missing --flag-started/--flag-mid/--flag-done")
        return 2

    # Beat 1: dialogue choice -> started flag
    started_args = argparse.Namespace(
        scene_path=start_scene,
        speaker_id=speaker_id,
        choice_id=choice_id,
        choice_text=choice_text,
        set_flag=flag_started,
        require=[],
        forbid=[flag_started],
        toast=started_toast,
        toast_seconds=3.0,
    )
    code = scene_commands._handle_scene_add_dialogue_choice_flag(started_args)
    if code != 0:
        return int(code)

    # Beat 2: interior trigger -> mid flag
    mid_zone_id = f"ObjectiveZone_{_sanitize_entity_id_token(flag_mid)}"
    mid_args = argparse.Namespace(
        scene_path=interior_scene,
        x=interior_x,
        y=interior_y,
        radius=interior_radius,
        zone_id=mid_zone_id,
        set_flag=flag_mid,
        require=[flag_started],
        forbid=[flag_mid],
        toast=mid_toast,
        toast_seconds=3.0,
    )
    code = scene_commands._handle_scene_add_triggerzone_objective(mid_args)
    if code != 0:
        return int(code)

    # Beat 3: cellar trigger -> done flag
    done_zone_id = f"ObjectiveZone_{_sanitize_entity_id_token(flag_done)}"
    done_args = argparse.Namespace(
        scene_path=cellar_scene,
        x=cellar_x,
        y=cellar_y,
        radius=cellar_radius,
        zone_id=done_zone_id,
        set_flag=flag_done,
        require=[flag_mid],
        forbid=[flag_done],
        toast=done_toast,
        toast_seconds=5.0,
    )
    code = scene_commands._handle_scene_add_triggerzone_objective(done_args)
    if code != 0:
        return int(code)

    print("[Mesh][CLI] Objective scaffolded successfully.")
    return 0

def _handle_wizard(args: argparse.Namespace) -> int:
    """Run the content wizard."""
    cmd_args = [args.subcommand]

    # Map args
    if args.name:
        cmd_args.extend(["--name", args.name])
    if args.name_prefix:
        cmd_args.extend(["--name-prefix", args.name_prefix])
    if args.perks:
        cmd_args.extend(["--perks", args.perks])

    if args.scene: cmd_args.extend(["--scene", args.scene])
    if args.pack: cmd_args.extend(["--pack", args.pack])
    if args.plan: cmd_args.extend(["--plan", args.plan])
    if args.apply: cmd_args.append("--apply")
    if args.dry_run: cmd_args.append("--dry-run")
    if args.into_world: cmd_args.extend(["--into-world", args.into_world])
    if getattr(args, "world", None): cmd_args.extend(["--world", args.world])
    if args.link_from: cmd_args.extend(["--link-from", args.link_from])
    if args.profile: cmd_args.extend(["--profile", args.profile])
    if args.npc_role: cmd_args.extend(["--npc-role", args.npc_role])
    if args.quest_type: cmd_args.extend(["--quest-type", args.quest_type])
    if args.vars:
        cmd_args.append("--vars")
        cmd_args.extend(args.vars)
    if args.run: cmd_args.extend(["--run", args.run])
    if args.list: cmd_args.append("--list")
    if args.template: cmd_args.extend(["--template", args.template])
    if args.theme: cmd_args.extend(["--theme", args.theme])
    if args.preset: cmd_args.extend(["--preset", args.preset])
    if args.with_boss: cmd_args.append("--with-boss")
    if args.with_puzzle: cmd_args.append("--with-puzzle")
    
    return wizard_command.main(cmd_args)

def _handle_docs(args: argparse.Namespace) -> int:
    """Run the documentation generator."""
    # Reconstruct argv for the tool's main function
    tool_argv = []
    if args.verify:
        tool_argv.append("--verify")
    
    from engine.tooling import generate_docs as docs_generator
    return docs_generator.main(tool_argv)

def _handle_dump_state(args: argparse.Namespace) -> int:
    """Dump deterministic state snapshot."""
    from engine.game import GameWindow

    config = load_config()
    window = GameWindow(
        width=config.width,
        height=config.height,
        title=config.title,
        fullscreen=config.fullscreen,
        vsync=config.vsync,
        config=config,
        config_path="config.json",
    )
    try:
        with suppress_stdout():
            window.load_scene(config.start_scene)
            payload = state_dump.dump_state(window)
        out_path = getattr(args, "out", None)
        if out_path:
            with suppress_stdout():
                write_json_atomic(Path(out_path), payload, indent=2, sort_keys=True, trailing_newline=True)
        
        sys.stdout.write(dumps_json_deterministic(payload, indent=2, sort_keys=True, trailing_newline=True))
        return 0
    except Exception as exc:  # noqa: BLE001
        payload = {"ok": False, "code": 1, "error": "dump_state.failed"}
        sys.stdout.write(dumps_json_deterministic(payload, indent=2, sort_keys=True, trailing_newline=True))
        return 1
    finally:
        try:
            window.close()
        except Exception:
            pass
