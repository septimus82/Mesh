from __future__ import annotations

import pytest

import engine.optional_arcade as optional_arcade
from engine.config import EngineConfig
from engine.game import GameWindow
from tests._game_window_live import dispose_game_window

pytestmark = [pytest.mark.fast]


def test_showcase_hub_sproutling_renders_visible_pixel() -> None:
    """Sproutling prop spawns, animates, and draws a non-background pixel on screen."""
    cfg = EngineConfig(
        width=1280,
        height=720,
        title="sproutling render contract",
        fullscreen=False,
        vsync=False,
        start_scene="scenes/showcase_hub.json",
        main_menu_scene=None,
        world_file=None,
    )
    try:
        window = GameWindow(width=1280, height=720, title=cfg.title, vsync=False, config=cfg)
    except TypeError as exc:
        if "OpenGLArcadeContext" in str(exc):
            pytest.skip("OpenGL context unavailable in this test runner session")
        raise
    try:
        window.render_batching_enabled = False
        window.render_culling_enabled = False
        window.scene_controller.load_scene("scenes/showcase_hub.json")
        main_menu = getattr(window, "main_menu_overlay", None)
        if main_menu is not None and getattr(main_menu, "visible", False):
            main_menu.close()

        sprout = next(
            sprite
            for sprite in window.scene_controller.layers["entities"]
            if (getattr(sprite, "mesh_entity_data", {}) or {}).get("id") == "hub_sproutling"
        )
        assert getattr(sprout, "mesh_animator", None) is not None

        for _ in range(10):
            window.on_update(1.0 / 60.0)
        window.clear()
        window.camera_controller.camera.position = (640.0, 360.0)
        with window.lighting.begin():
            window.scene_controller.draw()
        window.lighting.end()

        arcade = optional_arcade.arcade
        sx = int(sprout.center_x)
        sy = int(sprout.center_y)
        pixel = arcade.get_pixel(sx, sy, components=4)
        assert pixel[3] == 255
        assert pixel[:3] != (0, 0, 0)
    finally:
        dispose_game_window(window)
