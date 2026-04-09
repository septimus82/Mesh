import json
import types
from pathlib import Path
from unittest.mock import MagicMock

import arcade

from engine.input_controller import InputController
from engine.ui import (
    GoldenSliceVariantPickerOverlay,
    build_golden_slice_variant_picker_source,
)
from engine.ui_controller import UIController
from tests._typing import as_any


def test_variant_picker_missing_showcase_disables_selection(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"presets": {}}, sort_keys=True), encoding="utf-8")

    source = build_golden_slice_variant_picker_source(json.loads(config_path.read_text(encoding="utf-8")))
    assert source["ok"] is False
    assert "No variants available" in (source["message"] or "")
    assert source["names"] == []
    assert isinstance(source.get("categories"), list)

    window = types.SimpleNamespace()
    window.config_path = str(config_path)
    window.width = 800
    window.height = 600
    window.engine_config = types.SimpleNamespace(input_bindings=None)
    window.ui_controller = UIController(as_any(window))
    window.player_hud = types.SimpleNamespace(enqueue_toast=MagicMock())

    picker = GoldenSliceVariantPickerOverlay(as_any(window))
    picker.set_visible(True)
    assert picker.visible is True
    assert picker._entries == []
    assert "No variants available" in (picker._status_message or "")
    assert picker.on_key_press(arcade.key.ENTER, 0) is True
    assert picker.visible is True


def test_variant_picker_detects_run_preset_cycle() -> None:
    config = {
        "presets": {
            "golden_slice_index": {"steps": [{"cmd": "run-preset", "args": ["preset_a"]}]},
            "preset_a": {"steps": [{"cmd": "run-preset", "args": ["golden_slice_index"]}]},
        }
    }
    source = build_golden_slice_variant_picker_source(config)
    assert source["ok"] is False
    assert "recursion" in (source["message"] or "").lower()
    assert source["names"] == []


def test_variant_picker_missing_preset_is_marked_missing_and_safe(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "presets": {
                    "golden_slice_index": {"steps": [{"cmd": "run-preset", "args": ["missing_preset"]}]}
                }
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    window = types.SimpleNamespace()
    window.config_path = str(config_path)
    window.width = 800
    window.height = 600
    window.engine_config = types.SimpleNamespace(input_bindings=None)
    window.ui_controller = UIController(as_any(window))
    window.player_hud = types.SimpleNamespace(enqueue_toast=MagicMock())
    window.request_scene_change = MagicMock()

    picker = GoldenSliceVariantPickerOverlay(as_any(window))
    picker.set_visible(True)
    assert picker.visible is True
    assert len(picker._entries) == 1
    assert picker._entries[0]["name"] == "missing_preset"
    assert picker._entries[0]["missing"] is True

    assert picker.on_key_press(arcade.key.ENTER, 0) is True
    window.request_scene_change.assert_not_called()


def test_variant_picker_blocks_movement_dispatch_when_open(monkeypatch) -> None:
    monkeypatch.setenv("MESH_ACTIVE_PRESET", "golden_slice")

    window = types.SimpleNamespace()
    window.config_path = "config.json"
    window.width = 800
    window.height = 600
    window.engine_config = types.SimpleNamespace(input_bindings=None)
    window.ui_controller = UIController(as_any(window))
    window.player_hud = types.SimpleNamespace(enqueue_toast=MagicMock())

    dummy = types.SimpleNamespace(calls=0)
    dummy.blocks_input = False

    def _dummy_on_key_press(key: int, modifiers: int) -> bool:  # noqa: ARG001
        dummy.calls += 1
        return False

    dummy.on_key_press = _dummy_on_key_press
    window.ui_controller.register_ui_element(dummy)

    picker = GoldenSliceVariantPickerOverlay(as_any(window))
    picker.visible = True
    window.ui_controller.register_ui_element(picker)

    dispatch = MagicMock(return_value=True)
    monkeypatch.setattr("engine.input_controller.dispatch_action", dispatch)

    controller = InputController(as_any(window))
    controller.manager.press(arcade.key.W)
    controller.update(0.016)
    dispatch.assert_not_called()

    handled = window.ui_controller.on_key_press(arcade.key.ESCAPE, 0)
    assert handled is True
    assert picker.visible is False
    assert dummy.calls == 0
