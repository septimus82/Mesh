from __future__ import annotations

import types

from engine.console_controller import ConsoleController


def test_history_empty() -> None:
    controller = ConsoleController(types.SimpleNamespace())
    assert controller.history_previous() is None
    assert controller.history_next() is None


def test_history_push_dedup_and_navigation() -> None:
    controller = ConsoleController(types.SimpleNamespace())
    controller._history_push("one")
    controller._history_push("one")
    controller._history_push("two")
    assert controller.history == ["one", "two"]

    assert controller.history_next() == ""
    assert controller.history_previous() == "two"
    assert controller.history_previous() == "one"
    assert controller.history_previous() == "one"

    assert controller.history_next() == "two"
    assert controller.history_next() == ""
    assert controller.history_next() == ""


def test_history_trim_is_deterministic() -> None:
    controller = ConsoleController(types.SimpleNamespace())
    controller.max_lines = 3
    for item in ["a", "b", "c", "d", "e"]:
        controller._history_push(item)

    assert controller.history == ["c", "d", "e"]
    assert controller.history_index is None

