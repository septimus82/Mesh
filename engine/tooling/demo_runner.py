from __future__ import annotations

from engine.config import load_config
from engine.game import GameWindow


def launch_demo(start_scene: str | None = None, world_path: str | None = None) -> int:
    """Launch the Mesh Showcase demo (same behavior as `mesh demo`)."""
    try:
        config = load_config()
        config.debug_mode = True
        
        if start_scene:
            config.start_scene = start_scene
        
        if world_path:
            config.world_file = world_path

        window = GameWindow(
            width=config.width,
            height=config.height,
            title=config.title,
            fullscreen=config.fullscreen,
            vsync=config.vsync,
            config=config,
            config_path="config.json",
        )
        window.load_scene(config.start_scene)
        
        # Close the main menu for demo mode (it's auto-opened in GameWindow.__init__)
        if hasattr(window, "main_menu_overlay"):
            window.main_menu_overlay.close()

        window.run()
        return 0
    except Exception as e:  # noqa: BLE001  # REASON: demo-launch failures should report the error and return a controlled nonzero exit code
        print(f"Error launching demo: {e}")
        return 1
