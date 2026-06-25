"""Core and Misc commands."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from engine.config import load_config
from engine.logging_tools import suppress_stdout
from engine.persistence_io import dumps_json_deterministic, write_json_atomic
from engine.swallowed_exceptions import _log_swallow
from engine.tooling import state_dump, wizard_command
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
    if args.command == "mcp":
        from . import mcp_setup

        return mcp_setup.handle(args)
    if args.command == "dump-state":
        return _handle_dump_state(args)
    if args.command == "build-web":
        return _handle_build_web(args)
    if args.command == "web-smoke":
        return _handle_web_smoke(args)
    if args.command == "package-player":
        return _handle_package_player(args)
    return 1

def register(subparsers: argparse._SubParsersAction) -> None:
    # Play
    play_parser = subparsers.add_parser("play", help="Launch the game")
    play_parser.add_argument("scene_path", nargs="?", help="Optional start scene")

    # Runtime-only play smoke
    play_runtime_parser = subparsers.add_parser(
        "play-runtime",
        help="Launch runtime-only scene bootstrap (no editor wiring)",
    )
    play_runtime_parser.add_argument("scene_path", nargs="?", help="Optional start scene")
    play_runtime_parser.add_argument(
        "--headless-smoke",
        action="store_true",
        help="Run deterministic runtime smoke mode and exit",
    )
    play_runtime_parser.add_argument("--smoke-scene", help="Optional scene path override for --headless-smoke")
    play_runtime_parser.add_argument("--smoke-ticks", type=int, default=3, help="Tick count for smoke mode")
    play_runtime_parser.add_argument("--smoke-artifact", help="Optional JSON artifact path for smoke mode")
    play_runtime_parser.add_argument(
        "--diagnostics-artifact",
        help="Optional JSON artifact path for deterministic diagnostics snapshot on exit",
    )
    play_runtime_parser.add_argument(
        "--print-diagnostics-on-exit",
        action="store_true",
        help="Print a deterministic diagnostics summary at shutdown",
    )
    play_runtime_parser.set_defaults(func=_handle_play_runtime)

    build_web_parser = subparsers.add_parser("build-web", help="Build web target via pygbag")
    build_web_parser.add_argument("--entrypoint", default="web_main.py", help="Web entry point script")
    build_web_parser.add_argument(
        "--out",
        help="Optional output directory to copy web build artifacts into (e.g., artifacts/web_build)",
    )
    build_web_parser.add_argument(
        "--extra-arg",
        action="append",
        default=[],
        help="Extra argument passed through to tooling.build_web (repeatable)",
    )
    build_web_parser.add_argument(
        "--disable-sound-format-error",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Pass pygbag --disable-sound-format-error (default: enabled)",
    )
    build_web_parser.set_defaults(func=_handle_build_web)

    web_smoke_parser = subparsers.add_parser(
        "web-smoke",
        help="Validate built web output structure and emit deterministic smoke artifact",
    )
    web_smoke_parser.add_argument(
        "--build-dir",
        help="Optional web build directory override (defaults to pygbag.toml output or build/web)",
    )
    web_smoke_parser.add_argument(
        "--artifact",
        help="Optional JSON artifact path (e.g., artifacts/web_smoke.json)",
    )
    web_smoke_parser.set_defaults(func=_handle_web_smoke)

    package_player_parser = subparsers.add_parser(
        "package-player",
        help="Build a deterministic player-only runtime package (no editor modules)",
    )
    package_player_parser.add_argument(
        "--out",
        required=True,
        help="Output package directory (e.g., artifacts/player_pkg)",
    )
    package_player_parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run runtime smoke against the packaged bundle",
    )
    package_player_parser.add_argument(
        "--manifest",
        help="Optional manifest path override (default: <out>/manifest.json)",
    )
    package_player_parser.add_argument(
        "--diagnostics-artifact",
        help="Optional diagnostics artifact path for packaged runtime smoke (requires --smoke)",
    )
    package_player_parser.set_defaults(func=_handle_package_player)

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
    docs_parser.add_argument("--out-dir", default="docs", help="Directory where markdown files should be written")
    docs_parser.add_argument("--verify", action="store_true", help="Verify docs are up to date")

    # MCP onboarding
    mcp_parser = subparsers.add_parser("mcp", help="Configure an MCP client for this Mesh project")
    mcp_subparsers = mcp_parser.add_subparsers(dest="mcp_command", help="MCP subcommand")
    mcp_config_parser = mcp_subparsers.add_parser("config", help="Print an MCP client config snippet")
    mcp_config_parser.set_defaults(func=_handle_mcp)
    mcp_install_parser = mcp_subparsers.add_parser("install", help="Install Mesh into an MCP client config")
    mcp_install_parser.add_argument(
        "--client",
        choices=("claude-desktop",),
        default="claude-desktop",
        help="MCP client to configure",
    )
    mcp_install_parser.add_argument(
        "--config-path",
        help=argparse.SUPPRESS,
    )
    mcp_install_parser.set_defaults(func=_handle_mcp)

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
    except Exception as exc:  # noqa: BLE001  # REASON: misc CLI should collapse unexpected scene-load failures into a deterministic startup error
        print(f"[Mesh][CLI] Failed to load scene '{config.start_scene}': {exc}")
        return 1

    window.run()
    return 0


def _handle_play_runtime(args: argparse.Namespace) -> int:
    """Run the runtime-only bootstrap path without importing editor modules."""
    from engine.runtime_only import run_runtime_scene

    return int(
        run_runtime_scene(
            scene_path=getattr(args, "scene_path", None),
            headless_smoke=bool(getattr(args, "headless_smoke", False)),
            smoke_scene=getattr(args, "smoke_scene", None),
            smoke_ticks=int(getattr(args, "smoke_ticks", 3)),
            smoke_artifact=getattr(args, "smoke_artifact", None),
            diagnostics_artifact=getattr(args, "diagnostics_artifact", None),
            print_diagnostics_on_exit=bool(getattr(args, "print_diagnostics_on_exit", False)),
        )
    )


def _handle_build_web(args: argparse.Namespace) -> int:
    entrypoint = str(getattr(args, "entrypoint", "web_main.py") or "web_main.py").strip() or "web_main.py"
    passthrough = [str(item) for item in (getattr(args, "extra_arg", None) or []) if str(item).strip()]
    disable_sound_format_error = bool(getattr(args, "disable_sound_format_error", True))
    cmd = [sys.executable, "-m", "tooling.build_web", entrypoint]
    out_dir = str(getattr(args, "out", "") or "").strip()
    if out_dir:
        cmd.extend(["--out-dir", out_dir])
    cmd.append("--disable-sound-format-error" if disable_sound_format_error else "--no-disable-sound-format-error")
    for arg in passthrough:
        cmd.extend(["--extra-arg", arg])
    result = subprocess.run(cmd)
    if int(result.returncode) != 0:
        return int(result.returncode)

    if out_dir:
        return 0

    return 0


def _handle_web_smoke(args: argparse.Namespace) -> int:
    from .web_smoke import run_web_smoke

    return int(
        run_web_smoke(
            build_dir=getattr(args, "build_dir", None),
            artifact_path=getattr(args, "artifact", None),
        )
    )


def _handle_package_player(args: argparse.Namespace) -> int:
    from .player_package import package_player_bundle

    return int(
        package_player_bundle(
            out_dir=str(getattr(args, "out", "") or "").strip(),
            manifest_path=getattr(args, "manifest", None),
            smoke=bool(getattr(args, "smoke", False)),
            smoke_diagnostics_artifact=getattr(args, "diagnostics_artifact", None),
        )
    )


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
    tool_argv = ["--out-dir", str(getattr(args, "out_dir", "docs") or "docs")]
    if args.verify:
        tool_argv.append("--verify")

    from engine.tooling import generate_docs as docs_generator
    return docs_generator.main(tool_argv)


def _handle_mcp(args: argparse.Namespace) -> int:
    from . import mcp_setup

    return mcp_setup.handle(args)


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
    except Exception:  # noqa: BLE001  # REASON: dump-state CLI should emit a deterministic failure payload when runtime state export fails unexpectedly
        payload = {"ok": False, "code": 1, "error": "dump_state.failed"}
        sys.stdout.write(dumps_json_deterministic(payload, indent=2, sort_keys=True, trailing_newline=True))
        return 1
    finally:
        try:
            window.close()
        except Exception:
            _log_swallow("MISC-001", "mesh_cli/misc.py pass-only blanket swallow")
            pass
