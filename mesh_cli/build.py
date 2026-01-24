"""Build & Tooling commands for Mesh Engine."""

import argparse

from engine.tooling import (
    build_demo_command,
    cli_snapshot_command,
    content_commands,
    dist_command,
    golden_slice_scaffold,
    pack_commands,
    release_command,
    replay_goldens_command,
)


def register(subparsers: argparse._SubParsersAction) -> None:
    # Register commands from tooling modules
    build_demo_command.add_build_demo_command(subparsers)
    content_commands.add_content_commands(subparsers)
    golden_slice_scaffold.add_golden_slice_command(subparsers)
    pack_commands.add_pack_commands(subparsers)
    release_command.add_release_command(subparsers)
    cli_snapshot_command.add_cli_snapshot_command(subparsers)
    dist_command.add_dist_command(subparsers)
    replay_goldens_command.add_replay_goldens_command(subparsers)


def handle(args: argparse.Namespace) -> int:
    if args.command == "build-demo":
        return build_demo_command.handle_build_demo(args)
    
    # Handle commands that use set_defaults(func=...)
    if hasattr(args, "func"):
        result = args.func(args)
        return int(result) if isinstance(result, int) else 0
        
    return 1
