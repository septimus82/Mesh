from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class InputDispatch(Protocol):
    def on_key_press(self, window: Any, key: int, modifiers: int) -> None: ...
    def on_key_release(self, window: Any, key: int, modifiers: int) -> None: ...
    def on_mouse_motion(self, window: Any, x: float, y: float, dx: float, dy: float) -> None: ...
    def on_mouse_drag(
        self,
        window: Any,
        x: float,
        y: float,
        dx: float,
        dy: float,
        buttons: int,
        modifiers: int,
    ) -> None: ...
    def on_mouse_release(self, window: Any, x: float, y: float, button: int, modifiers: int) -> None: ...
    def on_mouse_press(self, window: Any, x: float, y: float, button: int, modifiers: int) -> None: ...
    def on_mouse_scroll(self, window: Any, x: float, y: float, scroll_x: float, scroll_y: float) -> None: ...
    def on_text(self, window: Any, text: str) -> None: ...


@dataclass(frozen=True, slots=True)
class InputService:
    """Deterministic orchestration facade for window input dispatch."""

    dispatch: InputDispatch

    def on_key_press(self, window: Any, key: int, modifiers: int) -> None:
        self.dispatch.on_key_press(window, int(key), int(modifiers))

    def on_key_release(self, window: Any, key: int, modifiers: int) -> None:
        self.dispatch.on_key_release(window, int(key), int(modifiers))

    def on_mouse_motion(self, window: Any, x: float, y: float, dx: float, dy: float) -> None:
        self.dispatch.on_mouse_motion(window, float(x), float(y), float(dx), float(dy))

    def on_mouse_drag(
        self,
        window: Any,
        x: float,
        y: float,
        dx: float,
        dy: float,
        buttons: int,
        modifiers: int,
    ) -> None:
        self.dispatch.on_mouse_drag(
            window,
            float(x),
            float(y),
            float(dx),
            float(dy),
            int(buttons),
            int(modifiers),
        )

    def on_mouse_release(self, window: Any, x: float, y: float, button: int, modifiers: int) -> None:
        self.dispatch.on_mouse_release(window, float(x), float(y), int(button), int(modifiers))

    def on_mouse_press(self, window: Any, x: float, y: float, button: int, modifiers: int) -> None:
        self.dispatch.on_mouse_press(window, float(x), float(y), int(button), int(modifiers))

    def on_mouse_scroll(self, window: Any, x: float, y: float, scroll_x: float, scroll_y: float) -> None:
        self.dispatch.on_mouse_scroll(window, float(x), float(y), float(scroll_x), float(scroll_y))

    def on_text(self, window: Any, text: str) -> None:
        self.dispatch.on_text(window, str(text))


def build_input_service(dispatch: InputDispatch | None = None) -> InputService:
    if dispatch is None:
        from engine.game_runtime import input_dispatch as dispatch_runtime

        dispatch = dispatch_runtime
    return InputService(dispatch=dispatch)

