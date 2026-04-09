from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from engine.event_runtime.emit import emit_event
from tests._typing import as_any


@dataclass
class _CaptureWindow:
    events: list[object] = field(default_factory=list)

    def emit_event(self, event: object) -> None:
        self.events.append(event)


def test_payload_none_normalizes_to_empty_dict() -> None:
    window = _CaptureWindow()
    emit_event(window, "test_event", None)
    assert len(window.events) == 1
    event = window.events[0]
    assert getattr(event, "type") == "test_event"
    assert getattr(event, "payload") == {}


def test_payload_is_shallow_copied() -> None:
    window = _CaptureWindow()
    payload = {"a": 1}
    emit_event(window, "test_event", payload)
    payload["a"] = 2
    event = window.events[0]
    assert getattr(event, "payload") == {"a": 1}


def test_bad_payload_type_has_deterministic_error_string() -> None:
    window = _CaptureWindow()
    with pytest.raises(TypeError) as excinfo:
        emit_event(window, "test_event", payload=as_any(["nope"]))
    assert str(excinfo.value) == "payload must be a dict, got list"
