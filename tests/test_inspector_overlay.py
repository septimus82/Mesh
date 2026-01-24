import types
from unittest.mock import MagicMock

import arcade

from engine.input_controller import InputController
from engine.ui import (
    INSPECTOR_MAX_LINE_CHARS,
    INSPECTOR_MAX_LINES,
    InspectorOverlay,
    build_inspector_lines,
)
from engine.ui_controller import UIController


def test_inspector_toggle_flips_visibility() -> None:
    window = types.SimpleNamespace(width=800, height=600)
    overlay = InspectorOverlay(window)  # type: ignore[arg-type]

    assert overlay.visible is False
    overlay.toggle()
    assert overlay.visible is True
    overlay.toggle()
    assert overlay.visible is False


def test_build_inspector_lines_is_deterministic_and_capped() -> None:
    dump = {
        "preset_id": "golden_slice_variant_d",
        "world_file": "worlds/" + ("x" * 400) + ".json",
        "scene_path": "packs/core_regions/scenes/" + ("y" * 400) + ".json",
        "gold": "12",
        "flags_count": 123,
        "flags_sample": ["flag_b", "flag_a", "flag_a", "flag_c"],
        "last_zone_id": None,
        "active_quest_ids": [
            "quest_z",
            "quest_a",
            "quest_b",
            "quest_c",
            "quest_d",
            "quest_e",
            "quest_f",
            "quest_g",
        ],
    }

    first = build_inspector_lines(dump)
    second = build_inspector_lines(dump)

    assert first == second
    assert 1 <= len(first) <= INSPECTOR_MAX_LINES
    assert all(isinstance(line, str) for line in first)
    assert all(len(line) <= INSPECTOR_MAX_LINE_CHARS for line in first)


def test_inspector_visible_does_not_block_movement_dispatch(monkeypatch) -> None:
    # Build a minimal stub window with real UIController so input_blocked reflects UI elements.
    window = types.SimpleNamespace()
    window.width = 800
    window.height = 600
    window.show_debug = False
    window.player_hud = types.SimpleNamespace(enqueue_toast=MagicMock())

    window.engine_config = types.SimpleNamespace(
        input_bindings={
            "move_up": ["W"],
            "toggle_inspector": ["I"],
        }
    )
    window.config_path = "config.json"

    window.ui_controller = UIController(window)  # type: ignore[arg-type]

    overlay = InspectorOverlay(window)  # type: ignore[arg-type]
    overlay.set_visible(True)
    window.ui_controller.register_ui_element(overlay)

    # Patch dispatch_action at the import site used by InputController.
    mock_dispatch = MagicMock(return_value=True)
    monkeypatch.setattr("engine.input_controller.dispatch_action", mock_dispatch)

    controller = InputController(window)  # type: ignore[arg-type]

    controller.manager.press(arcade.key.W)
    controller.update(0.016)

    mock_dispatch.assert_any_call(window, "move_up")
