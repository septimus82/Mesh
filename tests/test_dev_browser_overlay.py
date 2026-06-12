import types
from unittest.mock import MagicMock

import engine.optional_arcade as optional_arcade
from engine.input_controller import InputController
from engine.ui import (
    DEV_BROWSER_NO_RESULTS_MESSAGE,
    DevBrowserOverlay,
    filter_dev_browser_items,
)
from engine.ui_controller import UIController
from tests._typing import as_any


def _stub_window_for_input(*, bindings: dict[str, list[str]]):
    window = types.SimpleNamespace()
    window.width = 800
    window.height = 600
    window.show_debug = False
    window.config_path = "config.json"
    window.engine_config = types.SimpleNamespace(input_bindings=bindings)

    window.player_hud = types.SimpleNamespace(enqueue_toast=MagicMock())
    window.console_controller = types.SimpleNamespace(
        active=False,
        toggle=MagicMock(),
        process_key=MagicMock(return_value=False),
    )
    window.editor_controller = types.SimpleNamespace(
        active=False,
        handle_input=MagicMock(return_value=False),
        handle_text_input=MagicMock(),
    )

    window.ui_controller = UIController(as_any(window))
    return window


def test_dev_browser_toggle_flips_visibility() -> None:
    window = types.SimpleNamespace(width=800, height=600)
    overlay = DevBrowserOverlay(as_any(window))

    assert overlay.visible is False
    overlay.toggle()
    assert overlay.visible is True
    overlay.toggle()
    assert overlay.visible is False


def test_dev_browser_modal_capture_blocks_movement_and_esc_closes(monkeypatch) -> None:
    window = _stub_window_for_input(
        bindings={
            "move_up": ["W"],
            "toggle_dev_browser": ["B"],
        }
    )

    overlay = DevBrowserOverlay(as_any(window))
    overlay.set_visible(True)
    window.ui_controller.register_ui_element(overlay)

    mock_dispatch = MagicMock(return_value=True)
    monkeypatch.setattr("engine.input_controller.dispatch_action", mock_dispatch)

    controller = InputController(as_any(window))

    controller.manager.press(optional_arcade.arcade.key.W)
    controller.update(0.016)

    # Movement must not dispatch while the modal overlay is open.
    assert not any(call.args[1] == "move_up" for call in mock_dispatch.mock_calls)

    consumed = controller.on_key_press(optional_arcade.arcade.key.ESCAPE, 0)
    assert consumed is True
    assert overlay.visible is False


def test_dev_browser_filtering_is_deterministic_and_stable_order() -> None:
    source = [
        {"label": "worlds/main_world.json", "world_path": "worlds/main_world.json"},
        {"label": "worlds/act1_chapter1.json", "world_path": "worlds/act1_chapter1.json"},
        {"label": "worlds/hollowmere.json", "world_path": "worlds/hollowmere.json"},
    ]

    first = filter_dev_browser_items(source, "WORLD")
    second = filter_dev_browser_items(source, "WORLD")

    assert first == second
    # Stable order: preserved from source
    assert [e["label"] for e in first] == [e["label"] for e in source]


def test_dev_browser_no_results_message_when_filter_excludes_all() -> None:
    window = types.SimpleNamespace(width=800, height=600)
    overlay = DevBrowserOverlay(as_any(window))

    overlay.visible = True
    overlay.mode = "worlds"
    overlay._world_items = [
        {"label": "main — worlds/main_world.json", "world_path": "worlds/main_world.json"}
    ]
    overlay.filter_text = "zzz"
    overlay.selected_index = 0

    overlay._apply_filter()
    assert overlay._items == []
    assert overlay._status_message == DEV_BROWSER_NO_RESULTS_MESSAGE
