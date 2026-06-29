from __future__ import annotations

from typing import TYPE_CHECKING

import engine.optional_arcade as optional_arcade

if TYPE_CHECKING:
    from engine.game import GameWindow


def on_key_press(window: "GameWindow", key: int, modifiers: int) -> None:  # noqa: ARG001
    editor = getattr(window, "editor_controller", None)
    editor_active = editor is not None and getattr(editor, "active", False)

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

    # Block all input while an editor build is in progress.
    if editor is not None and getattr(getattr(editor, "build_session", None), "is_running", False):
        return

    session = getattr(editor, "play_session", None) if editor is not None else None
    if key == optional_arcade.arcade.key.ESCAPE and session is not None and getattr(session, "is_playing", False):
        stopper = getattr(editor, "stop_playing", None)
        if callable(stopper):
            stopper()
        return

    # First-launch tour: intercept Enter (advance) and Esc (skip) when the tour is active.
    # Guard with editor.active so keys are not swallowed during main-menu / project-browser.
    tour = getattr(editor, "tour", None) if editor_active else None
    if tour is not None and getattr(tour, "is_active", False):
        if key in (optional_arcade.arcade.key.RETURN, optional_arcade.arcade.key.ENTER,
                   optional_arcade.arcade.key.NUM_ENTER):
            advance = getattr(tour, "advance", None)
            if callable(advance):
                advance()
            return
        elif key == optional_arcade.arcade.key.ESCAPE:
            skip = getattr(tour, "skip", None)
            if callable(skip):
                skip()
            return

    # Find-everything: Ctrl+K (tracked-key modifier) or F1 (function-key, no MOD_CTRL dependency)
    if editor_active:
        _build = getattr(editor, "build_session", None)
        _play = getattr(editor, "play_session", None)
        if not getattr(_build, "is_running", False) and not getattr(_play, "is_playing", False):
            _toggle_fe = getattr(editor, "toggle_find_everything", None)
            if callable(_toggle_fe):
                _input_ctrl = getattr(window, "input_controller", None)
                _keys_down = getattr(_input_ctrl, "get_keys_down", lambda: set())() if _input_ctrl is not None else set()
                _is_ctrl_k = key == optional_arcade.arcade.key.K and optional_arcade.arcade.key.LCTRL in _keys_down
                _is_f1 = key == optional_arcade.arcade.key.F1
                if _is_ctrl_k or _is_f1:
                    _toggle_fe()
                    return

    if key == optional_arcade.arcade.key.F6:
        if editor_active:
            play_from_here = getattr(editor, "play_from_here", None)
            if callable(play_from_here):
                play_from_here()
            return

    # When the editor is active, give it first chance at general key input.
    _editor_handle = getattr(editor, "handle_input", None) if editor_active else None
    if callable(_editor_handle):
        if _editor_handle(key, modifiers):
            return
    if editor_active:
        if key == optional_arcade.arcade.key.ESCAPE:
            return

    # UI has priority outside editor mode.
    if not editor_active and window.ui_controller.on_key_press(key, modifiers):
        return

    if (
        not editor_active
        and key == optional_arcade.arcade.key.M
        and (modifiers & optional_arcade.arcade.key.MOD_CTRL)
    ):
        opener = getattr(window, "open_monster_party_view", None)
        if callable(opener):
            opener()
        return

    if key == optional_arcade.arcade.key.ESCAPE:
        overlay = getattr(window, "settings_overlay", None)
        toggle = getattr(overlay, "toggle", None) if overlay is not None else None
        if callable(toggle):
            toggle()
            return

    if key == optional_arcade.arcade.key.F12:
        if bool(getattr(window.engine_config, "debug_mode", False)):
            if modifiers & optional_arcade.arcade.key.MOD_SHIFT:
                starter = getattr(window, "start_debug_trainer_monster_battle", None)
            else:
                starter = getattr(window, "start_debug_monster_battle", None)
            if callable(starter):
                starter()
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
    _editor = getattr(window, "editor_controller", None)
    if _editor is not None and getattr(getattr(_editor, "build_session", None), "is_running", False):
        return
    window.input_controller.on_mouse_press(x, y, button, modifiers)


def on_mouse_scroll(window: "GameWindow", x: float, y: float, scroll_x: float, scroll_y: float) -> None:
    handler = getattr(window.input_controller, "on_mouse_scroll", None)
    if callable(handler):
        handler(x, y, scroll_x, scroll_y)


def on_text(window: "GameWindow", text: str) -> None:
    window.input_controller.on_text(text)
