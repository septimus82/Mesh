"""CLI command: ``mesh new_project <name> <dest>``

Creates a schema-valid blank Mesh project (``engine.project_scaffold`` + blank template).

Example::

    mesh new_project my_game C:/Games
    cd C:/Games/my_game && mesh play
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _engine_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _inside_engine(path: Path) -> bool:
    root = _engine_root().resolve()
    return path == root or root in path.parents


def default_dest(dest: str | Path) -> Path:
    """Where to create a project when the user gave ``dest`` (``"."`` unless they chose one).

    New games stay out of the engine folder: run from inside it without a destination,
    they go to Documents/Mesh Projects instead.
    """
    chosen = Path(dest).resolve()
    if str(dest) == "." and _inside_engine(chosen):
        from engine.projects import default_projects_dir  # noqa: PLC0415

        return default_projects_dir()
    return chosen


def create_blank_project(name: str, dest: Path, *, template_id: str = "blank", force: bool = False) -> int:
    project_dir = (dest / name).resolve()
    if _inside_engine(project_dir):
        print(f"[mesh] Error: '{project_dir}' is inside the Mesh engine folder. Keep games separate: "
              "pass --dest with a folder outside it (or run without --dest to use Documents/Mesh Projects).",
              file=sys.stderr)
        return 1

    if project_dir.exists():
        if any(project_dir.iterdir()):
            if not force:
                print(
                    f"[mesh] Error: '{project_dir}' already exists and is not empty. "
                    "Pass --force to overwrite.",
                    file=sys.stderr,
                )
                return 1
            import shutil

            shutil.rmtree(project_dir)

    from engine.project_scaffold import create_project, validate_new_project_target

    valid, message = validate_new_project_target(project_dir)
    if not valid:
        print(f"[mesh] Error: {message}", file=sys.stderr)
        return 1

    create_project(project_dir, name, template_id=template_id)
    try:
        shown = project_dir.relative_to(Path.cwd().resolve())
    except ValueError:
        shown = project_dir
    print(f"Created {project_dir}")
    print("Next:")
    print(f"  cd {shown}")
    print("  mesh play     walk around (WASD, E to talk)")
    print("  mesh edit     open it in the editor (Shift+F5 for Creator Mode)")
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
    dest = default_dest(getattr(args, "dest", "."))
    return create_blank_project(
        str(args.name),
        dest,
        template_id=str(getattr(args, "template", "blank")),
        force=bool(getattr(args, "force", False)),
    )
