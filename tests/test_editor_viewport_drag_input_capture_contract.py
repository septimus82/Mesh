from __future__ import annotations

import engine.optional_arcade as optional_arcade
from engine.config import EngineConfig
from engine.game import GameWindow
from engine.input_runtime import capture as input_capture
from tests._game_window_live import dispose_game_window

pytestmark = [__import__("pytest").mark.fast]


def test_editor_viewport_drag_moves_entity_through_input_capture() -> None:
    """Press → drag → release on a viewport entity must move it (real input path)."""
    cfg = EngineConfig(
        width=1280,
        height=720,
        title="editor drag contract",
        fullscreen=False,
        vsync=False,
        start_scene="scenes/showcase_hub.json",
        main_menu_scene=None,
        world_file=None,
    )
    window = GameWindow(width=1280, height=720, title=cfg.title, vsync=False, config=cfg)
    try:
        window.scene_controller.load_scene("scenes/showcase_hub.json")
        main_menu = getattr(window, "main_menu_overlay", None)
        if main_menu is not None and getattr(main_menu, "visible", False):
            main_menu.close()

        editor = window.editor_controller
        editor.toggle()
        assert editor.active is True

        portal = next(
            sprite
            for sprite in window.scene_controller.layers["entities"]
            if (getattr(sprite, "mesh_entity_data", {}) or {}).get("id") == "portal_lighting"
        )
        start_x = float(portal.center_x)
        start_y = float(portal.center_y)
        screen_x = start_x - float(window.camera_controller.camera.position[0]) + window.width / 2
        screen_y = start_y - float(window.camera_controller.camera.position[1]) + window.height / 2

        ic = window.input_controller
        assert input_capture.handle_mouse_press(
            ic,
            screen_x,
            screen_y,
            optional_arcade.arcade.MOUSE_BUTTON_LEFT,
            0,
        )
        assert editor.selected_entity is portal
        assert editor.entity_dragging is True

        input_capture.handle_mouse_drag(
            ic,
            screen_x + 48.0,
            screen_y + 32.0,
            48.0,
            32.0,
            optional_arcade.arcade.MOUSE_BUTTON_LEFT,
            0,
        )
        assert (portal.center_x, portal.center_y) != (start_x, start_y)

        input_capture.handle_mouse_release(
            ic,
            screen_x + 48.0,
            screen_y + 32.0,
            optional_arcade.arcade.MOUSE_BUTTON_LEFT,
            0,
        )
        assert editor.entity_dragging is False
        assert editor.undo_stack
        assert editor.undo_stack[-1]["type"] == "MoveEntity"
    finally:
        dispose_game_window(window)


def test_ai_chat_overlay_does_not_consume_viewport_clicks_when_inactive_tab() -> None:
    cfg = EngineConfig(
        width=1280,
        height=720,
        title="ai chat click contract",
        fullscreen=False,
        vsync=False,
        start_scene="scenes/showcase_hub.json",
        main_menu_scene=None,
        world_file=None,
    )
    window = GameWindow(width=1280, height=720, title=cfg.title, vsync=False, config=cfg)
    try:
        window.scene_controller.load_scene("scenes/showcase_hub.json")
        editor = window.editor_controller
        editor.toggle()
        overlay = window.ai_chat_overlay
        assert overlay.on_mouse_press(680.0, 400.0, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is False
    finally:
        dispose_game_window(window)
