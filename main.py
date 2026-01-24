"""Main entry point for the Mesh 2D game engine demo."""

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


def main() -> None:
    """Initialize Arcade, load the test scene, and start the game loop."""
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
    initial_scene = config.main_menu_scene if config.main_menu_scene else config.start_scene
    spawn_id = None
    wc = getattr(window, "world_controller", None)
    if wc is not None:
        start_key = wc.get_start_scene_key()
        path = wc.get_scene_path(start_key) if start_key else None
        if path:
            initial_scene = path
            spawn_id = wc.get_start_spawn()
            window.game_state_controller.set_var("world_id", wc.id)
            window.game_state_controller.set_var("world_scene_key", start_key)
            if spawn_id:
                window.set_next_spawn_point(spawn_id)

    # Capture the scene data for future systems (debug overlays, hot reload, etc.).
    scene_data: Dict[str, Any] = window.load_scene(initial_scene)
    _ = scene_data  # Placeholder until we expose scene metadata to other systems.

    window.run()


if __name__ == "__main__":
    main()
