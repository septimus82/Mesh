"""One guard for the CLI commands that write a project's files in place (#462 A-04).

Studio, ``author apply``, ``apply-plan`` and the AI/MCP paths own a project while they write it
(``engine.editor.project_ownership``). The older commands listed here did not, so they could write behind an open Mesh
Studio. ``dispatch`` asks ``own_for_write`` once, before any handler runs: the command either owns the project for its
whole run or is refused (non-zero, nothing written). ``apply-plan`` / ``undo-last-plan`` take ownership themselves.

The set is a table: a new in-place writer must be added here (``tests/test_cli_write_guard.py`` holds the cases).
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

# commands (``args.command``) that write project files, whatever their options
WRITE_COMMANDS = frozenset({"new-npc", "place-npc", "new-quest", "new-behaviour", "add-puzzle", "new-prefab",
                            "place-prefab"})
# (command, subcommand) pairs, the subcommand read from ``<command>_command``
WRITE_SUBCOMMANDS = frozenset({("world", "add-scene"), ("world", "link-scenes"), ("room", "scaffold")})
# scene-family handlers (``args.func.__name__``) that write the scene file
WRITE_SCENE_HANDLERS = frozenset({
    "_handle_new_scene", "_handle_edit_scene", "_handle_tidy_scene", "_handle_scene_create",
    "_handle_scene_tilemap_add_layer", "_handle_scene_tilemap_remove_layer", "_handle_scene_tilemap_init",
    "_handle_scene_tilemap_resize", "_handle_scene_tilemap_flood_fill", "_handle_scene_tilemap_fill_rect",
    "_handle_scene_tilemap_clear_rect", "_handle_scene_tilemap_paint", "_handle_scene_tilemap_brush",
    "_handle_scene_backgrounds_add_layer", "_handle_scene_backgrounds_remove_layer", "_handle_scene_add_placeholder",
    "_handle_scene_add_entity", "_handle_scene_add_triggerzone_objective", "_handle_scene_add_dialogue_choice_flag",
    "_handle_scene_stamp", "_handle_scene_macro_apply", "_handle_scene_prefab_reset"})

_PATH_ATTRS = ("scene_path", "into", "path", "world_path", "world", "from_scene", "scene")


def writes_project(args: argparse.Namespace) -> bool:
    command = getattr(args, "command", None)
    if command in WRITE_COMMANDS:
        return True
    if (command, getattr(args, f"{command}_command", None)) in WRITE_SUBCOMMANDS:
        return True
    if command == "schema-fix-ids":
        return not getattr(args, "dry_run", False)
    if command == "migrate":
        return bool(getattr(args, "write", False))
    if command == "auto-wire-transitions":
        return bool(getattr(args, "apply", False))
    return getattr(getattr(args, "func", None), "__name__", "") in WRITE_SCENE_HANDLERS


def _project_start(args: argparse.Namespace) -> Path:
    """Where the command writes: the file it names, else the folder it runs in."""
    for attr in _PATH_ATTRS:
        value = getattr(args, attr, None)
        if isinstance(value, str) and value:
            path = Path(value).expanduser()
            return path if path.is_dir() else path.parent
    return Path.cwd()


def own_for_write(args: argparse.Namespace) -> tuple[bool, Any]:
    """``(proceed, ownership)``: ``(True, None)`` for a command that writes nothing in place or sits in no Mesh
    project (no editor can own it), ``(True, held)`` once owned (release it after), ``(False, None)`` once refused."""
    if not writes_project(args):
        return True, None
    from engine.editor import project_ownership as po  # noqa: PLC0415  # (heavy package: only when writing)

    root = po.project_root(_project_start(args))
    if root is None:
        return True, None
    command = str(args.command)
    try:
        return True, po.acquire(root, po.AUTHORING, wait=0.5)
    except (po.OwnedElsewhere, po.OwnershipUnavailable) as exc:
        print("[Mesh][CLI] " + po.refused_write(command, exc))
        return False, None
