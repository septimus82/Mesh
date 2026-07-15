from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine.editor.creator_mode import CreatorModeController, build_creator_overlay_model
from engine.editor.creator_mode.creator_overlay_renderer import (
    _GLYPH_WIDTH_RATIO,
    _panel_char_limit,
    build_creator_overlay_draw_commands,
)
from engine.ui_overlays.common import text_char_capacity_for_width

pytestmark = pytest.mark.fast


def _overlay_layout(width: float, height: float) -> tuple[float, float, float]:
    win_w = max(320.0, float(width))
    pad = min(14.0, max(8.0, win_w * 0.03))
    side_gap = 8.0
    left_w = min(180.0, max(96.0, win_w * 0.28))
    max_right_w = max(112.0, win_w - left_w - side_gap)
    right_w = min(480.0, max(112.0, win_w * 0.34), max_right_w)
    right_text_width = max(1.0, right_w - 2.0 * pad)
    bottom_text_width = max(1.0, win_w - (pad + 8.0) - pad)
    return right_text_width, bottom_text_width, win_w


def _door_entity(config: dict[str, object] | None = None) -> dict[str, object]:
    return {
        "id": "door_north",
        "name": "North Gate",
        "behaviours": ["SceneTransition"],
        "behaviour_config": {
            "SceneTransition": dict(
                config
                if config is not None
                else {
                    "target_scene": "town",
                    "spawn_id": "north_gate_entry",
                }
            )
        },
    }


def test_right_panel_text_respects_panel_width_at_font_size() -> None:
    long_scene = "scenes/deep/nested/path/" + ("segment/" * 20) + "lighting_showcase.json"
    controller = CreatorModeController(
        SimpleNamespace(
            selected_entity=_door_entity(config={"target_scene": long_scene, "spawn_id": "entry"}),
            window=SimpleNamespace(scene_controller=SimpleNamespace(current_scene_path="forest")),
        )
    )
    controller.show()
    width, height = 1280, 720
    right_text_width, _, win_w = _overlay_layout(width, height)
    commands = build_creator_overlay_draw_commands(
        build_creator_overlay_model(controller.build_snapshot()),
        width,
        height,
    )

    for command in commands:
        if command.kind != "text" or command.region != "right":
            continue
        capacity = text_char_capacity_for_width(
            right_text_width,
            command.font_size,
            glyph_width_ratio=_GLYPH_WIDTH_RATIO,
        )
        assert len(command.text) <= capacity
        right_edge = command.x + len(command.text) * command.font_size * _GLYPH_WIDTH_RATIO
        assert right_edge <= win_w


def test_right_panel_path_field_uses_middle_truncation() -> None:
    long_scene = "scenes/deep/nested/path/" + ("segment/" * 20) + "lighting_showcase.json"
    controller = CreatorModeController(
        SimpleNamespace(
            selected_entity=_door_entity(config={"target_scene": long_scene, "spawn_id": "entry"}),
            window=SimpleNamespace(scene_controller=SimpleNamespace(current_scene_path="forest")),
        )
    )
    controller.show()
    commands = build_creator_overlay_draw_commands(
        build_creator_overlay_model(controller.build_snapshot()),
        1280,
        720,
    )
    destination_lines = [
        command.text
        for command in commands
        if command.kind == "text" and command.region == "right" and command.text.startswith("Destination Map:")
    ]
    assert destination_lines
    line = destination_lines[0]
    assert "..." in line
    assert line.startswith("Destination Map: scenes/")
    assert line.endswith("lighting_showcase.json")


def test_panel_char_limit_never_exceeds_width_capacity() -> None:
    right_text_width = 320.0
    for font_size in (10, 11, 12, 13):
        limit = _panel_char_limit(right_text_width, font_size, 68)
        assert limit <= text_char_capacity_for_width(
            right_text_width,
            font_size,
            glyph_width_ratio=_GLYPH_WIDTH_RATIO,
        )


def test_bottom_panel_text_stays_within_window() -> None:
    controller = CreatorModeController(SimpleNamespace(selected_entity=None))
    controller.show()
    width, height = 800, 600
    _, bottom_text_width, win_w = _overlay_layout(width, height)
    commands = build_creator_overlay_draw_commands(
        build_creator_overlay_model(controller.build_snapshot()),
        width,
        height,
    )

    for command in commands:
        if command.kind != "text" or command.region != "bottom":
            continue
        capacity = text_char_capacity_for_width(
            bottom_text_width,
            command.font_size,
            glyph_width_ratio=_GLYPH_WIDTH_RATIO,
        )
        assert len(command.text) <= max(capacity, _panel_char_limit(bottom_text_width, command.font_size, 92))
        right_edge = command.x + len(command.text) * command.font_size * _GLYPH_WIDTH_RATIO
        assert right_edge <= win_w
