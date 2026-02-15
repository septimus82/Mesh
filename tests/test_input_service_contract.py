from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from engine.services.input_service import InputService


@dataclass
class _RecorderDispatch:
    events: list[dict[str, Any]] = field(default_factory=list)

    def _record(self, name: str, payload: dict[str, Any]) -> None:
        self.events.append({"name": name, "payload": payload})

    def on_key_press(self, window: Any, key: int, modifiers: int) -> None:  # noqa: ARG002
        self._record("key_press", {"key": key, "modifiers": modifiers})

    def on_key_release(self, window: Any, key: int, modifiers: int) -> None:  # noqa: ARG002
        self._record("key_release", {"key": key, "modifiers": modifiers})

    def on_mouse_motion(self, window: Any, x: float, y: float, dx: float, dy: float) -> None:  # noqa: ARG002
        self._record("mouse_motion", {"x": x, "y": y, "dx": dx, "dy": dy})

    def on_mouse_drag(
        self,
        window: Any,
        x: float,
        y: float,
        dx: float,
        dy: float,
        buttons: int,
        modifiers: int,
    ) -> None:  # noqa: ARG002
        self._record(
            "mouse_drag",
            {
                "x": x,
                "y": y,
                "dx": dx,
                "dy": dy,
                "buttons": buttons,
                "modifiers": modifiers,
            },
        )

    def on_mouse_release(self, window: Any, x: float, y: float, button: int, modifiers: int) -> None:  # noqa: ARG002
        self._record("mouse_release", {"x": x, "y": y, "button": button, "modifiers": modifiers})

    def on_mouse_press(self, window: Any, x: float, y: float, button: int, modifiers: int) -> None:  # noqa: ARG002
        self._record("mouse_press", {"x": x, "y": y, "button": button, "modifiers": modifiers})

    def on_mouse_scroll(self, window: Any, x: float, y: float, scroll_x: float, scroll_y: float) -> None:  # noqa: ARG002
        self._record("mouse_scroll", {"x": x, "y": y, "scroll_x": scroll_x, "scroll_y": scroll_y})

    def on_text(self, window: Any, text: str) -> None:  # noqa: ARG002
        self._record("text", {"text": text})


def _digest(events: list[dict[str, Any]]) -> str:
    blob = json.dumps(events, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _run_script(service: InputService) -> list[dict[str, Any]]:
    window = object()
    service.on_key_press(window, key=65, modifiers=2)
    service.on_mouse_motion(window, x=1, y=2, dx=3, dy=4)
    service.on_mouse_drag(window, x=5, y=6, dx=7, dy=8, buttons=1, modifiers=0)
    service.on_mouse_press(window, x=9, y=10, button=1, modifiers=4)
    service.on_mouse_release(window, x=11, y=12, button=1, modifiers=4)
    service.on_mouse_scroll(window, x=13, y=14, scroll_x=0, scroll_y=-1)
    service.on_key_release(window, key=65, modifiers=2)
    service.on_text(window, text="ok")
    return list(service.dispatch.events)


def test_input_service_is_deterministic_for_same_input_script() -> None:
    dispatch_a = _RecorderDispatch()
    dispatch_b = _RecorderDispatch()
    service_a = InputService(dispatch=dispatch_a)
    service_b = InputService(dispatch=dispatch_b)

    events_a = _run_script(service_a)
    events_b = _run_script(service_b)

    assert events_a == events_b
    assert _digest(events_a) == _digest(events_b)

