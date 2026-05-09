"""CLI command: ``mesh new <name>``

Creates a runnable starter game project in a new directory:

  mesh new my_game
  cd my_game && python main.py

The generated project contains:
- main.py          — minimal engine entry point
- config.json      — minimum valid EngineConfig
- scenes/          — one starter room with player + NPC
- dialogue/        — NPC dialogue script
- README.md        — how to run and edit
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Template content (bundled inline — no separate template directory needed)
# ---------------------------------------------------------------------------

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
    initial_scene = config.main_menu_scene or config.start_scene
    window.load_scene(initial_scene)
    __import__("arcade").run()


if __name__ == "__main__":
    main()
'''

_CONFIG_JSON: dict[str, Any] = {
    "start_scene": "scenes/starter_room.json",
    "main_menu_scene": None,
    "world_file": None,
    "width": 1280,
    "height": 720,
    "title": "{name}",
}

_STARTER_ROOM_JSON: dict[str, Any] = {
    "name": "Starter Room",
    "settings": {
        "background_color": "dark_blue_gray",
        "music": None,
        "music_volume": 1.0,
    },
    "entities": [
        {
            "id": "starter_player_128_128_0_0",
            "name": "Player",
            "tag": "player",
            "x": 128.0,
            "y": 128.0,
            "sprite": "assets/sprites/animated_player.png",
            "sprite_sheet": {
                "columns": 4,
                "rows": 2,
                "frame_width": 64,
                "frame_height": 64,
            },
            "animations": {
                "idle": {"fps": 4, "frames": [0, 1, 2, 3], "loop": True},
                "walk": {"fps": 8, "frames": [4, 5, 6, 7], "loop": True},
            },
            "behaviours": ["PlayerController", "CameraFollow"],
            "behaviour_config": {
                "CameraFollow": {"padding": 12, "zoom": 1.0},
            },
        },
        {
            "id": "starter_npc_320_128_0_0",
            "name": "Guide",
            "tag": "npc",
            "x": 320.0,
            "y": 128.0,
            "sprite": "assets/sprites/animated_player.png",
            "sprite_sheet": {
                "columns": 4,
                "rows": 2,
                "frame_width": 64,
                "frame_height": 64,
            },
            "animations": {
                "idle": {"fps": 2, "frames": [0, 1], "loop": True},
            },
            "behaviours": ["Dialogue"],
            "behaviour_config": {
                "Dialogue": {
                    "dialogue_lines": [],
                    "dialogue": {
                        "speaker": "Guide",
                        "start": "root",
                        "nodes": {
                            "root": {
                                "text": "Hi! Welcome to your new Mesh game.\nPress E to interact with things.",
                                "choices": "  ",
                            },
                        },
                    },
                },
            },
        },
    ],
    "layers": [
        {"name": "background"},
        {"name": "entities"},
        {"name": "foreground"},
    ],
}

_README = """\
# {name}

A starter Mesh game project.

## Running

Make sure you have the Mesh venv activated, then:

```
cd {name}
python main.py
```

## Controls

- **WASD** — move
- **E** — interact / talk to NPCs
- **F4** — toggle editor
- **F3** — toggle debug overlay

## Editing

- Open `scenes/starter_room.json` to add entities, tiles, and triggers.
- Open `config.json` to change the window title, size, or start scene.
- Run `python -m mesh_cli scene create ...` to scaffold new scenes.

## Next steps

- Add more scenes and link them with scene-transition entities.
- Add dialogue to your NPCs by editing `behaviour_config.Dialogue.dialogue`.
- Run `python -m mesh_cli --help` to see all available CLI tools.
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_project(name: str, dest: Path, *, force: bool = False) -> int:
    """Create a new starter game project.

    Parameters
    ----------
    name:
        Project name — used as the directory name and substituted into
        template strings.
    dest:
        Parent directory in which to create the project folder.
    force:
        When *True*, overwrite an existing directory.

    Returns
    -------
    int
        0 on success, non-zero on failure.
    """
    project_dir = dest / name

    if project_dir.exists() and not force:
        print(
            f"[mesh new] Error: '{project_dir}' already exists. "
            f"Pass --force to overwrite.",
            file=sys.stderr,
        )
        return 1

    if project_dir.exists() and force:
        shutil.rmtree(project_dir)

    # Create directory structure
    (project_dir / "scenes").mkdir(parents=True)
    (project_dir / "dialogue").mkdir(parents=True)
    (project_dir / "assets" / "sprites").mkdir(parents=True)

    # main.py
    (project_dir / "main.py").write_text(
        _MAIN_PY.replace("{name}", name), encoding="utf-8"
    )

    # config.json
    cfg = _deep_substitute(_CONFIG_JSON, name)
    (project_dir / "config.json").write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # scenes/starter_room.json
    (project_dir / "scenes" / "starter_room.json").write_text(
        json.dumps(_STARTER_ROOM_JSON, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # README.md
    (project_dir / "README.md").write_text(
        _README.replace("{name}", name), encoding="utf-8"
    )

    # Copy bundled player sprite from engine assets (same repo)
    _copy_sprite(project_dir)

    print(f"Created {project_dir}/")
    print(f"Run with:  cd {name} && python main.py")
    return 0


def _deep_substitute(obj: Any, name: str) -> Any:
    """Recursively replace '{name}' in all string values."""
    if isinstance(obj, str):
        return obj.replace("{name}", name)
    if isinstance(obj, dict):
        return {k: _deep_substitute(v, name) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deep_substitute(v, name) for v in obj]
    return obj


def _copy_sprite(project_dir: Path) -> None:
    """Copy the bundled animated_player sprite into the project."""
    # Walk up from this file to find the repo root (assets/ lives at repo root)
    here = Path(__file__).parent
    candidates = [
        here.parent / "assets" / "sprites" / "animated_player.png",
        Path("assets") / "sprites" / "animated_player.png",
    ]
    src: Path | None = next((p for p in candidates if p.exists()), None)

    dest_sprite = project_dir / "assets" / "sprites" / "animated_player.png"
    if src is not None:
        shutil.copy2(src, dest_sprite)
    else:
        # Placeholder: write a minimal 1×1 valid PNG (8-byte header + IHDR + IDAT + IEND)
        _write_placeholder_png(dest_sprite)


def _write_placeholder_png(dest: Path) -> None:
    """Write a minimal valid 1x1 transparent PNG as a placeholder sprite."""
    # Minimal 1x1 transparent PNG — no external dependency
    data = bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR length + "IHDR"
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,  # width=1, height=1
        0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4,  # 8-bit RGBA, CRC start
        0x89, 0x00, 0x00, 0x00, 0x0B, 0x49, 0x44, 0x41,  # CRC end, IDAT
        0x54, 0x78, 0x9C, 0x62, 0x00, 0x00, 0x00, 0x02,  # IDAT data
        0x00, 0x01, 0xE2, 0x21, 0xBC, 0x33, 0x00, 0x00,  # IDAT CRC
        0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE, 0x42,  # IEND
        0x60, 0x82,                                         # IEND CRC
    ])
    dest.write_bytes(data)


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

def register(subparsers: Any) -> None:
    p = subparsers.add_parser(
        "new",
        help="Create a new starter game project",
        description=(
            "Scaffold a runnable starter game project in a new directory.\n"
            "Example: mesh new my_game"
        ),
    )
    p.add_argument("name", help="Project name (also used as the directory name)")
    p.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the target directory if it already exists",
    )
    p.add_argument(
        "--dest",
        default=".",
        help="Parent directory to create the project in (default: current directory)",
    )


def handle(args: argparse.Namespace) -> int:
    dest = Path(getattr(args, "dest", ".")).resolve()
    force = bool(getattr(args, "force", False))
    name: str = args.name
    return create_project(name, dest, force=force)
