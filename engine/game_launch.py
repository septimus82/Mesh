"""Shared launch helpers for play and editor entry points."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from engine.config import load_config
from engine.game import GameWindow
from engine.game_runtime.scene_flow import resolve_game_start_scene
from engine.paths import pin_config, reset_path_caches
from engine.repo_root import is_standalone_project_root, pin_launched_project_root


def resolve_project_root(project_path: str | Path | None) -> Path:
    if project_path is None or not str(project_path).strip():
        return Path.cwd().resolve()
    root = Path(str(project_path)).expanduser().resolve()
    if root.is_file():
        root = root.parent
    return root


def launch_editor(
    *,
    project_root: str | Path | None = None,
    scene_path: str | None = None,
    open_tile_paint: bool = True,
) -> int:
    """Launch the game window with the in-game editor active for a project."""
    root = resolve_project_root(project_root)
    config_path = root / "config.json"
    if not config_path.is_file():
        print(f"[Mesh][CLI] Error: no config.json in project root: {root}")
        return 1

    previous_cwd = Path.cwd()
    os.chdir(root)
    reset_path_caches()

    config = load_config(str(config_path))
    pin_config(config)

    if is_standalone_project_root(root):
        pin_launched_project_root(root, config=config)

    window = GameWindow(
        width=config.width,
        height=config.height,
        title=config.title,
        fullscreen=config.fullscreen,
        vsync=config.vsync,
        config=config,
        config_path=str(config_path),
    )

    wc = getattr(window, "world_controller", None)
    initial_scene = (
        scene_path
        or resolve_game_start_scene(engine_config=config, world_controller=wc)
        or config.start_scene
    )

    try:
        scene_data: dict[str, Any] = window.load_scene(initial_scene)
    except Exception as exc:  # noqa: BLE001  # REASON: editor launch should report scene load failures before opening the window loop
        print(f"[Mesh][CLI] Failed to load scene '{initial_scene}': {exc}")
        os.chdir(previous_cwd)
        return 1

    editor = window.editor_controller
    editor._enable_editor_mode()

    if open_tile_paint:
        tile_ctrl = editor.tile_controller
        if tile_ctrl.tilemap_available():
            tilemap = scene_data.get("tilemap") if isinstance(scene_data, dict) else None
            collision_id = (
                tilemap.get("collision_layer_id")
                if isinstance(tilemap, dict)
                else None
            )
            tile_ctrl.refresh_tile_palette()
            if isinstance(collision_id, str) and collision_id in editor.tile_layers:
                editor.tile_layer_index = editor.tile_layers.index(collision_id)
            tile_ctrl.set_tile_panel_active(True)

    try:
        window.run()
    except KeyboardInterrupt:
        print("[Mesh] Shutdown requested — exiting cleanly.")
    finally:
        os.chdir(previous_cwd)
    return 0
