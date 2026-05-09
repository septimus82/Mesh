from __future__ import annotations

from typing import TYPE_CHECKING

import engine.optional_arcade as optional_arcade

if TYPE_CHECKING:
    from engine.game import GameWindow


def on_key_press(window: "GameWindow", key: int, modifiers: int) -> None:  # noqa: ARG001
    # Console toggle should work even when menus/UI are capturing input.
    if key in (optional_arcade.arcade.key.GRAVE, optional_arcade.arcade.key.INSERT):
        console = getattr(window, "console_controller", None)
        toggle = getattr(console, "toggle", None) if console is not None else None
        if callable(toggle):
            toggle()
        return

    # When the console is active, it should have first chance at Enter/Backspace/etc
    # even if UI overlays are visible (so commands can be submitted reliably).
    console = getattr(window, "console_controller", None)
    active = getattr(console, "active", False) if console is not None else False
    if isinstance(active, bool) and active:
        process_key = getattr(console, "process_key", None)
        if callable(process_key) and process_key(int(key), int(modifiers)):
            return

    editor = getattr(window, "editor_controller", None)
    session = getattr(editor, "play_session", None) if editor is not None else None
    if key == optional_arcade.arcade.key.ESCAPE and session is not None and getattr(session, "is_playing", False):
        stopper = getattr(editor, "stop_playing", None)
        if callable(stopper):
            stopper()
        return

    # UI has priority
    if window.ui_controller.on_key_press(key, modifiers):
        return

    if key == optional_arcade.arcade.key.F6:
        editor = getattr(window, "editor_controller", None)
        if editor is not None and getattr(editor, "active", False):
            play_from_here = getattr(editor, "play_from_here", None)
            if callable(play_from_here):
                play_from_here()
            return

    if key == optional_arcade.arcade.key.ESCAPE:
        overlay = getattr(window, "settings_overlay", None)
        toggle = getattr(overlay, "toggle", None) if overlay is not None else None
        if callable(toggle):
            toggle()
            return

    window.input_controller.on_key_press(key, modifiers)

    if window.game_over:
        return

    if key == optional_arcade.arcade.key.ESCAPE:
        window.paused = not window.paused
        window.pause_menu.toggle()
        window.pause_menu.visible = window.paused
        if window.paused:
            window.console_log("Game Paused")
        else:
            window.console_log("Game Resumed")
        return

    if key == optional_arcade.arcade.key.F9:
        enabled = bool(getattr(window, "render_batching_enabled", False))
        next_enabled = not enabled
        setattr(window, "render_batching_enabled", next_enabled)
        setattr(window, "render_culling_enabled", next_enabled)
        setattr(window, "tilemap_batching_enabled", next_enabled)
        window.console_log(
            f"Sprite batching {'enabled' if next_enabled else 'disabled'}"
        )
        return

    # Toggle debug overlay
    if key == optional_arcade.arcade.key.F3:
        window.engine_config.debug_mode = not window.engine_config.debug_mode


def on_key_release(window: "GameWindow", key: int, modifiers: int) -> None:  # noqa: ARG001
    window.input_controller.on_key_release(key, modifiers)


def on_mouse_motion(window: "GameWindow", x: float, y: float, dx: float, dy: float) -> None:
    window.input_controller.on_mouse_motion(x, y, dx, dy)


def on_mouse_drag(
    window: "GameWindow",
    x: float,
    y: float,
    dx: float,
    dy: float,
    buttons: int,
    modifiers: int,
) -> None:
    window.input_controller.on_mouse_drag(x, y, dx, dy, buttons, modifiers)


def on_mouse_release(window: "GameWindow", x: float, y: float, button: int, modifiers: int) -> None:
    window.input_controller.on_mouse_release(x, y, button, modifiers)


def on_mouse_press(window: "GameWindow", x: float, y: float, button: int, modifiers: int) -> None:
    window.input_controller.on_mouse_press(x, y, button, modifiers)


def on_mouse_scroll(window: "GameWindow", x: float, y: float, scroll_x: float, scroll_y: float) -> None:
    handler = getattr(window.input_controller, "on_mouse_scroll", None)
    if callable(handler):
        handler(x, y, scroll_x, scroll_y)


def on_text(window: "GameWindow", text: str) -> None:
    window.input_controller.on_text(text)
