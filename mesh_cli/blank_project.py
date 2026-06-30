"""CLI command: ``mesh new_project <name> <dest>``

Creates a schema-valid blank Mesh project (``engine.project_scaffold`` + blank template).

Example::

    python -m mesh_cli new_project my_game C:/Games
    cd C:/Games/my_game && python main.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def create_blank_project(name: str, dest: Path, *, template_id: str = "blank", force: bool = False) -> int:
    project_dir = (dest / name).resolve()

    if project_dir.exists():
        if any(project_dir.iterdir()):
            if not force:
                print(
                    f"[mesh new_project] Error: '{project_dir}' already exists and is not empty. "
                    "Pass --force to overwrite.",
                    file=sys.stderr,
                )
                return 1
            import shutil

            shutil.rmtree(project_dir)

    from engine.project_scaffold import create_project, validate_new_project_target

    valid, message = validate_new_project_target(project_dir)
    if not valid:
        print(f"[mesh new_project] Error: {message}", file=sys.stderr)
        return 1

    create_project(project_dir, name, template_id=template_id)
    print(f"Created {project_dir}/")
    print(f"Run with:  cd {project_dir} && python main.py")
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "new_project",
        help="Create a blank Mesh project from engine templates",
        description=(
            "Scaffold a schema-valid blank project using engine.project_scaffold.\n"
            "Example: python -m mesh_cli new_project my_game C:/Games"
        ),
    )
    parser.add_argument("name", help="Project name (also used as the window title)")
    parser.add_argument(
        "dest",
        nargs="?",
        default=".",
        help="Parent directory for the new project folder (default: current directory)",
    )
    parser.add_argument(
        "--template",
        default="blank",
        help="Template id from engine.project_templates (default: blank)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Remove an existing project directory before scaffolding",
    )


def handle(args: argparse.Namespace) -> int:
    dest = Path(getattr(args, "dest", ".")).resolve()
    return create_blank_project(
        str(args.name),
        dest,
        template_id=str(getattr(args, "template", "blank")),
        force=bool(getattr(args, "force", False)),
    )
