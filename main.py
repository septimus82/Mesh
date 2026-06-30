"""Main entry point for the Mesh 2D game engine demo."""

import argparse
import sys
import warnings
from collections import deque
from typing import Any, Dict

# Suppress arcade draw_text PerformanceWarning as refactoring all UI to Text objects is pending
warnings.filterwarnings("ignore", message=".*draw_text is an extremely slow function.*")

# Attempt to patch Pyglet for Python 3.13 compatibility
# This fixes AttributeError: 'list' object has no attribute 'popleft' in pyglet 1.5.x
try:
    import pyglet
    if sys.platform == "win32":
        import pyglet.window.win32
        _old_init = pyglet.window.win32.Win32Window.__init__

        def _new_init(self, *args, **kwargs):
            _old_init(self, *args, **kwargs)
            if hasattr(self, "_event_queue") and not isinstance(self._event_queue, deque):
                print(f"[Mesh][Patch] Converting _event_queue to deque for {self}")
                self._event_queue = deque(self._event_queue)

        pyglet.window.win32.Win32Window.__init__ = _new_init  # type: ignore
        print("[Mesh][Patch] Applied Pyglet Win32Window patch for Python 3.13")
except (ImportError, AttributeError) as e:
    print(f"[Mesh][Patch] Failed to apply Pyglet patch: {e}")
    pass

from engine.config import load_config
from engine.game import GameWindow
from engine.game_runtime.scene_flow import resolve_game_start_scene


def main() -> None:
    """Initialize Arcade, load the test scene, and start the game loop."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--edit",
        action="store_true",
        help="Open the in-game editor for this project (standalone entry)",
    )
    args, _unknown = parser.parse_known_args()
    if args.edit:
        from engine.game_launch import launch_editor

        raise SystemExit(launch_editor())

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

    # Determine initial scene
    spawn_id = None
    if config.main_menu_scene:
        initial_scene = config.main_menu_scene
    else:
        wc = getattr(window, "world_controller", None)
        project_start = resolve_game_start_scene(
            engine_config=config,
            world_controller=wc,
        )
        initial_scene = project_start or config.start_scene
        if wc is not None:
            start_key = wc.get_start_scene_key()
            if start_key and project_start is not None and project_start == initial_scene:
                spawn_id = wc.get_start_spawn()
                window.game_state_controller.set_var("world_id", wc.id)
                window.game_state_controller.set_var("world_scene_key", start_key)

    if spawn_id:
        window.set_next_spawn_point(spawn_id)

    # Capture the scene data for future systems (debug overlays, hot reload, etc.).
    scene_data: Dict[str, Any] = window.load_scene(initial_scene)
    _ = scene_data  # Placeholder until we expose scene metadata to other systems.

    try:
        window.run()
    except KeyboardInterrupt:
        print("[Mesh] Shutdown requested — exiting cleanly.")


if __name__ == "__main__":
    main()
