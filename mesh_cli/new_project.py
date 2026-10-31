"""CLI command: ``mesh new <name>``

The beginner front door. Creates a playable project through
``engine.project_scaffold`` (same path as ``new_project`` and the project
browser) using the ``starter`` template: a walkable player and a Guide NPC.

  mesh new my_game
  cd my_game
  mesh play
"""
from __future__ import annotations

import argparse
from typing import Any

from .blank_project import create_blank_project, default_dest


def register(subparsers: Any) -> None:
    p = subparsers.add_parser(
        "new",
        help="Create a new playable project",
        description=(
            "Create a playable Mesh project in a new folder.\n"
            "Example: mesh new my_game"
        ),
    )
    p.add_argument("name", help="Project name (also used as the folder name)")
    p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the target directory if it already exists",
    )
    p.add_argument(
        "--dest",
        default=".",
        help="Parent directory to create the project in (default: the current directory, "
        "or Documents/Mesh Projects when run inside the engine folder)",
    )
    p.add_argument(
        "--template",
        default="starter",
        help="Template id from engine.project_templates (default: starter)",
    )


def handle(args: argparse.Namespace) -> int:
    return create_blank_project(
        str(args.name),
        default_dest(getattr(args, "dest", ".")),
        template_id=str(getattr(args, "template", "starter")),
        force=bool(getattr(args, "force", False)),
    )
