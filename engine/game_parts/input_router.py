from __future__ import annotations

from typing import TYPE_CHECKING

from ._shared import resolve_input_service

if TYPE_CHECKING:
    import engine.optional_arcade


def lock_player_input(self, *, owner: str | None = None) -> None:
    self.input_controller.lock_player_input(owner=owner)


def unlock_player_input(self, *, owner: str | None = None) -> None:
    self.input_controller.unlock_player_input(owner=owner)


def clear_input_locks(self) -> None:
    self.input_controller.clear_input_locks()


def is_input_locked(self) -> bool:
    return self.input_controller.is_input_locked()


def player_input_blocked(self) -> bool:
    return self.input_controller.player_input_blocked()


def on_key_press(self, key: int, modifiers: int) -> None:
    resolve_input_service(self).on_key_press(self, key, modifiers)


def on_key_release(self, key: int, modifiers: int) -> None:
    resolve_input_service(self).on_key_release(self, key, modifiers)


def on_mouse_motion(self, x: float, y: float, dx: float, dy: float) -> None:
    resolve_input_service(self).on_mouse_motion(self, x, y, dx, dy)


def on_mouse_drag(
    self,
    x: float,
    y: float,
    dx: float,
    dy: float,
    buttons: int,
    modifiers: int,
) -> None:
    resolve_input_service(self).on_mouse_drag(self, x, y, dx, dy, buttons, modifiers)


def on_mouse_release(self, x: float, y: float, button: int, modifiers: int) -> None:
    resolve_input_service(self).on_mouse_release(self, x, y, button, modifiers)


def on_mouse_press(self, x: float, y: float, button: int, modifiers: int) -> None:
    resolve_input_service(self).on_mouse_press(self, x, y, button, modifiers)


def on_mouse_scroll(self, x: float, y: float, scroll_x: float, scroll_y: float) -> None:
    resolve_input_service(self).on_mouse_scroll(self, x, y, scroll_x, scroll_y)


def on_text(self, text: str) -> None:
    resolve_input_service(self).on_text(self, text)


def on_text_motion(self, motion: int) -> None:  # noqa: ARG001
    return


def get_pressed_keys(self) -> set[int]:
    return self.input_controller.get_keys_down()


def bind_input_router_methods(cls) -> None:
    cls.lock_player_input = lock_player_input
    cls.unlock_player_input = unlock_player_input
    cls.clear_input_locks = clear_input_locks
    cls.is_input_locked = is_input_locked
    cls.player_input_blocked = player_input_blocked
    cls.on_key_press = on_key_press
    cls.on_key_release = on_key_release
    cls.on_mouse_motion = on_mouse_motion
    cls.on_mouse_drag = on_mouse_drag
    cls.on_mouse_release = on_mouse_release
    cls.on_mouse_press = on_mouse_press
    cls.on_mouse_scroll = on_mouse_scroll
    cls.on_text = on_text
    cls.on_text_motion = on_text_motion
    cls.get_pressed_keys = get_pressed_keys