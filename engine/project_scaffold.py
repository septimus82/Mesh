"""Project scaffolding utilities for Mesh Engine."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from . import json_io
from .logging_tools import get_logger

_LOG = get_logger("engine.project_scaffold")

_MAIN_PY = '''\
"""Entry point for {name}."""

import sys
import warnings
from collections import deque

warnings.filterwarnings("ignore", message=".*draw_text is an extremely slow function.*")

try:
    import pyglet
    if sys.platform == "win32":
        import pyglet.window.win32
        _old_init = pyglet.window.win32.Win32Window.__init__

        def _new_init(self, *args, **kwargs):
            _old_init(self, *args, **kwargs)
            if hasattr(self, "_event_queue") and not isinstance(self._event_queue, deque):
                self._event_queue = deque(self._event_queue)

        pyglet.window.win32.Win32Window.__init__ = _new_init
except (ImportError, AttributeError):
    pass

from engine.config import load_config
from engine.game import GameWindow
from engine.game_runtime.scene_flow import resolve_game_start_scene


def main() -> None:
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
    if config.main_menu_scene:
        initial_scene = config.main_menu_scene
    else:
        wc = getattr(window, "world_controller", None)
        initial_scene = resolve_game_start_scene(
            engine_config=config,
            world_controller=wc,
        ) or config.start_scene
    window.load_scene(initial_scene)
    __import__("arcade").run()


if __name__ == "__main__":
    main()
'''

_MONSTER_STARTER_FILES = (
    "assets/data/monster_species.json",
    "assets/data/monster_moves.json",
    "assets/data/monster_type_chart.json",
    "assets/sprites/sproutling.png",
    "assets/sprites/shelltide.png",
    "assets/sprites/animated_player.png",
)


def validate_new_project_target(root: Path) -> tuple[bool, str]:
    """Check if the target directory is valid for a new project.

    Returns:
        (valid, error_message)
    """
    if not root.exists():
        return True, ""

    if not root.is_dir():
        return False, f"Target path exists and is not a directory: {root}"

    ignored = {".git", ".gitignore", ".vscode", ".idea", ".DS_Store"}
    items = [item for item in root.iterdir() if item.name not in ignored]
    if items:
        return False, f"Target directory is not empty: {root}"

    return True, ""


def _engine_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _copy_engine_asset(rel_path: str, dest_root: Path) -> None:
    src = _engine_root() / rel_path
    dest = dest_root / rel_path
    if not src.is_file():
        _LOG.warning("Engine starter asset missing: %s", src)
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def _copy_monster_starter_pack(root: Path) -> None:
    from .monster.battle_audio import default_battle_audio_asset_paths

    copied: set[str] = set()
    for rel_path in _MONSTER_STARTER_FILES:
        _copy_engine_asset(rel_path, root)
        copied.add(rel_path)
    for rel_path in default_battle_audio_asset_paths():
        if rel_path in copied:
            continue
        _copy_engine_asset(rel_path, root)


def create_project(root: Path, name: str, template_id: str = "blank") -> None:
    """Create a new Mesh project structure at the given root."""
    from .project_templates import apply_template

    _LOG.info("Creating new project '%s' at %s (template=%s)", name, root, template_id)

    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)

    dirs = [
        "packs/core_regions/scenes",
        "packs/core_regions/worlds",
        "assets/images",
        "assets/sprites",
        "assets/sounds",
        "assets/music",
        "assets/data",
        "artifacts",
    ]

    for directory in dirs:
        (root / directory).mkdir(parents=True, exist_ok=True)

    config: dict[str, Any] = {
        "content_roots": ["."],
        "width": 1280,
        "height": 720,
        "title": str(name),
        "start_scene": "packs/core_regions/scenes/start.json",
        "main_menu_scene": None,
        "world_file": "packs/core_regions/worlds/main.json",
        "lighting_enabled": True,
    }

    json_io.write_json_atomic(root / "config.json", config)
    (root / "main.py").write_text(_MAIN_PY.replace("{name}", str(name)), encoding="utf-8")

    world = {
        "id": "main",
        "name": "Main World",
        "start_scene": "start",
        "scenes": {
            "start": {
                "label": "Start",
                "path": "packs/core_regions/scenes/start.json",
                "tags": ["start"],
            },
        },
    }
    json_io.write_json_atomic(root / "packs/core_regions/worlds/main.json", world)

    apply_template(root, template_id)
    _copy_monster_starter_pack(root)

    _LOG.info("Project created successfully.")
