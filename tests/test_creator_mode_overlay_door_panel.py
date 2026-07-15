from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace

import pytest

from engine.editor.creator_mode import (
    CreatorModeController,
    build_creator_door_request_from_selection,
    build_creator_overlay_model,
    creator_door_staging,
)
from engine.editor.creator_mode.creator_overlay_renderer import (
    build_creator_overlay_draw_commands,
    truncate_creator_overlay_text,
)

pytestmark = pytest.mark.fast


def test_selected_non_door_keeps_existing_overlay_model_behavior() -> None:
    controller = CreatorModeController(_editor_with_selection({"name": "Rock", "behaviours": ["StaticSprite"]}))
    controller.show()

    model = build_creator_overlay_model(controller.build_snapshot())

    assert model.active is True
    assert model.selected_kind == "Thing"
    assert model.door_panel is None


def test_selected_door_with_valid_scene_exit_config_includes_door_panel() -> None:
    controller = CreatorModeController(_editor_with_selection(_door_entity()))
    controller.show()

    model = build_creator_overlay_model(controller.build_snapshot())

    assert model.door_panel is not None
    assert model.door_panel.title == "Door plan: North Gate"
    assert [section.title for section in model.door_panel.sections] == [
        "Plan",
        "What will happen",
        "Staging",
        "Problems",
        "Warnings",
    ]


def test_selected_door_with_valid_scene_exit_config_renders_door_panel_text() -> None:
    controller = CreatorModeController(_editor_with_selection(_door_entity()))
    controller.show()

    commands = build_creator_overlay_draw_commands(
        build_creator_overlay_model(controller.build_snapshot()),
        1280,
        720,
    )
    text = _command_text(commands)

    assert "Door plan: North Gate" in text
    assert "Plan" in text
    assert "What will happen" in text
    assert "Staging" in text
    assert "Problems" in text
    assert "Warnings" in text


def test_selected_door_with_missing_destination_includes_blocked_problem_line() -> None:
    entity = _door_entity(config={"spawn_id": "north_gate_entry"})
    controller = CreatorModeController(_editor_with_selection(entity))
    controller.show()

    model = build_creator_overlay_model(controller.build_snapshot())

    assert model.door_panel is not None
    assert model.door_panel.status == "blocked"
    assert _section_texts(model.door_panel, "Problems") == (
        "Door workflow is blocked.",
        "Destination scene is required.",
    )


def test_bridge_unavailable_renders_disabled_stage_proposal_display_state() -> None:
    controller = CreatorModeController(_editor_with_selection(_door_entity(), live_bridge=None))
    controller.show()

    commands = build_creator_overlay_draw_commands(
        build_creator_overlay_model(controller.build_snapshot()),
        1280,
        720,
    )
    text = _command_text(commands)

    assert "[Disabled] Stage Proposal - Proposal bridge is unavailable." in text


def test_fake_bridge_renders_ready_stage_proposal_without_calling_bridge() -> None:
    bridge = FakeBridge()
    controller = CreatorModeController(_editor_with_selection(_door_entity(), live_bridge=bridge))
    controller.show()

    commands = build_creator_overlay_draw_commands(
        build_creator_overlay_model(controller.build_snapshot()),
        1280,
        720,
    )

    assert "[Ready] Stage Proposal" in _command_text(commands)
    assert bridge.called is False


def test_rendering_projection_does_not_call_bridge_stage_pending_proposal() -> None:
    bridge = FakeBridge()
    controller = CreatorModeController(_editor_with_selection(_door_entity(), live_bridge=bridge))
    controller.show()

    build_creator_overlay_draw_commands(
        build_creator_overlay_model(controller.build_snapshot()),
        1280,
        720,
    )

    assert bridge.called is False


def test_rendering_projection_does_not_call_stage_creator_door_proposal(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args, **_kwargs):
        raise AssertionError("overlay must not stage")

    monkeypatch.setattr(creator_door_staging, "stage_creator_door_proposal", fail)
    controller = CreatorModeController(_editor_with_selection(_door_entity(), live_bridge=FakeBridge()))
    controller.show()

    model = build_creator_overlay_model(controller.build_snapshot())
    commands = build_creator_overlay_draw_commands(model, 1280, 720)

    assert "[Ready] Stage Proposal" in _command_text(commands)


def test_door_panel_overlay_output_is_deterministic() -> None:
    controller = CreatorModeController(_editor_with_selection(_door_entity(), live_bridge=FakeBridge()))
    controller.show()
    model = build_creator_overlay_model(controller.build_snapshot())

    first = _command_snapshot(build_creator_overlay_draw_commands(model, 1280, 720))
    second = _command_snapshot(build_creator_overlay_draw_commands(model, 1280, 720))

    assert first == second


def test_long_door_panel_lines_are_truncated_by_overlay_rules() -> None:
    long_scene = "very_long_destination_map_" * 8
    entity = _door_entity(config={"target_scene": long_scene, "spawn_id": "north_gate_entry"})
    controller = CreatorModeController(_editor_with_selection(entity, live_bridge=FakeBridge()))
    controller.show()

    commands = build_creator_overlay_draw_commands(
        build_creator_overlay_model(controller.build_snapshot()),
        1280,
        720,
    )
    text = _command_text(commands)

    assert long_scene not in text
    friendly_scene = long_scene.replace("_", " ").title()
    expected = f"- Configure selected door: Destination: {friendly_scene}."
    assert truncate_creator_overlay_text(expected, 68) in text


def test_door_selection_adapter_returns_none_for_non_door() -> None:
    assert build_creator_door_request_from_selection({"name": "Rock"}, source_scene="forest") is None


def test_package_import_still_does_not_import_renderer_module() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import engine.editor.creator_mode; "
                "print('engine.editor.creator_mode.creator_overlay_renderer' in sys.modules)"
            ),
        ],
        capture_output=True,
        check=True,
        text=True,
    )

    assert result.stdout.strip() == "False"


def test_pure_modules_do_not_import_real_bridge_modules() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "from engine.editor.creator_mode.creator_door_selection "
                "import build_creator_door_request_from_selection; "
                "from engine.editor.creator_mode.creator_door_panel "
                "import build_creator_door_panel; "
                "blocked = ["
                "'engine.editor.live_session_bridge', "
                "'engine.editor.editor_live_ops_controller', "
                "'engine.editor.proposal_inbox'"
                "]; "
                "print(any(name in sys.modules for name in blocked))"
            ),
        ],
        capture_output=True,
        check=True,
        text=True,
    )

    assert result.stdout.strip() == "False"


class FakeBridge:
    def __init__(self) -> None:
        self.called = False

    def stage_pending_proposal(self, ops):
        self.called = True
        raise AssertionError("read-only overlay must not stage")


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


def _editor_with_selection(entity: dict[str, object], live_bridge: object | None = None):
    return SimpleNamespace(
        selected_entity=entity,
        live_bridge=live_bridge,
        window=SimpleNamespace(scene_controller=SimpleNamespace(current_scene_path="forest")),
    )


def _section_texts(panel, title: str) -> tuple[str, ...]:
    for section in panel.sections:
        if section.title == title:
            return tuple(line.text for line in section.lines)
    raise AssertionError(f"missing section {title}")


def _command_text(commands) -> str:
    return "\n".join(command.text for command in commands if command.kind == "text")


def _command_snapshot(commands):
    return tuple((command.kind, command.region, command.text, command.x, command.y) for command in commands)
