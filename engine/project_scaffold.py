"""Project scaffolding utilities for Mesh Engine."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from . import json_io
from .logging_tools import get_logger

_LOG = get_logger("engine.project_scaffold")

_MAIN_PY = '''\
"""{name}: run the game with `python main.py` (or press Play in Mesh Studio)."""


def main() -> None:
    # The engine is imported here, after the DPI mode is set: pyglet fixes it when it
    # loads, and Mesh draws at a stable scale only when Windows doesn't rescale it.
    from engine.dpi_bootstrap import set_process_dpi_unaware

    set_process_dpi_unaware()

    from engine.config import load_config
    from engine.game import GameWindow
    from engine.game_runtime.scene_flow import resolve_game_start_scene

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
    start = config.main_menu_scene or resolve_game_start_scene(
        engine_config=config, world_controller=getattr(window, "world_controller", None)
    ) or config.start_scene
    window.load_scene(start)
    window.run()


if __name__ == "__main__":
    main()
'''

# Every new project gets these: the starter characters' sheet and the door the
# editor uses when it links two rooms (engine.project_ops.DOOR_SPRITE).
_STARTER_FILES = (
    "assets/sprites/animated_player.png",
    "assets/sprites/door.png",
    "assets/tilesets/starter.png",  # project_ops.TILESET_SOURCE and its image
    "assets/tilesets/starter.json",
)


def ensure_starter_files(root: Path) -> None:
    """Copy any missing starter file into an existing project (e.g. one made before maps)."""
    for rel_path in _STARTER_FILES:
        if not (Path(root) / rel_path).is_file():
            _copy_engine_asset(rel_path, Path(root))

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


def _engine_input_bindings() -> dict[str, Any]:
    try:
        data = json.loads((_engine_root() / "config.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _LOG.warning("Engine config.json unreadable; new project gets no input_bindings")
        return {}
    bindings = data.get("input_bindings") if isinstance(data, dict) else None
    return dict(bindings) if isinstance(bindings, dict) else {}


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
        # Off by default: with no lights in the scene the screen renders near-black.
        # lighting_playground turns it back on alongside its lights.
        "lighting_enabled": False,
    }
    # Explicit bindings: the runtime would fall back to defaults for {}, but
    # `mesh check`'s wiring gate reads config.json and needs every required action.
    engine_bindings = _engine_input_bindings()
    if engine_bindings:
        config["input_bindings"] = engine_bindings

    json_io.write_json_atomic(root / "config.json", config)
    safe_name = " ".join(str(name).replace("\\", "/").replace('"', "'").split())  # it goes into a docstring
    (root / "main.py").write_text(_MAIN_PY.replace("{name}", safe_name), encoding="utf-8")

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
    # Empty catalogs validate-all requires; without them every new project fails it.
    json_io.write_json_atomic(root / "assets/prefabs.json", [])
    json_io.write_json_atomic(root / "assets/data/events.json", {"events": []})

    apply_template(root, template_id)
    for rel_path in _STARTER_FILES:
        _copy_engine_asset(rel_path, root)
    # The monster game was a test project; only its own template ships its data.
    if template_id == "monster":
        _copy_monster_starter_pack(root)

    _LOG.info("Project created successfully.")
