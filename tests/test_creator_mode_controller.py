from __future__ import annotations

from copy import deepcopy
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import engine.optional_arcade as optional_arcade
from engine.config import EngineConfig
from engine.editor.creator_mode import (
    CreatorModeController,
    build_creator_overlay_model,
)
from engine.editor.creator_mode.creator_inspector import build_creator_inspector
import engine.editor.creator_mode.creator_overlay_renderer as creator_overlay_renderer
from engine.editor.creator_mode.creator_overlay_renderer import (
    build_creator_overlay_draw_commands,
    draw_creator_overlay,
    truncate_creator_overlay_text,
)
from engine.editor.creator_mode.creator_terms import classify_entity_snapshot, friendly_engine_term
from engine.editor_controller import EditorModeController
from engine.game_runtime import input_dispatch

pytestmark = pytest.mark.fast


def test_controller_starts_inactive() -> None:
    controller = CreatorModeController()

    assert controller.active is False
    assert controller.build_snapshot().active is False


def test_creator_mode_package_import_does_not_import_renderer() -> None:
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


def test_toggle_show_hide_change_active_state() -> None:
    controller = CreatorModeController()

    assert controller.toggle() is True
    assert controller.active is True

    controller.hide()
    assert controller.active is False

    controller.show()
    assert controller.active is True


def test_snapshot_contains_friendly_shell_labels() -> None:
    controller = CreatorModeController()
    snapshot = controller.build_snapshot()

    assert snapshot.top_actions == ("Save", "Test Play", "Fix Problems", "Advanced Mode")
    assert snapshot.left_tools == (
        "Map",
        "Person",
        "Door",
        "Monster Area",
        "Battle",
        "Quest",
        "Item",
        "Light",
    )
    assert snapshot.bottom_panel_title == "Things to Fix"
    assert snapshot.selected_kind == "Thing"


def test_snapshot_summarizes_selected_entity_without_mutation() -> None:
    entity_data = {
        "id": "door_1",
        "name": "North Gate",
        "behaviours": ["SceneTransition"],
        "behaviour_config": {"SceneTransition": {"target_scene": "town"}},
    }
    before = deepcopy(entity_data)
    editor = SimpleNamespace(selected_entity=SimpleNamespace(mesh_entity_data=entity_data))
    controller = CreatorModeController(editor)

    snapshot = controller.build_snapshot()

    assert snapshot.selected_kind == "Door"
    assert snapshot.selected_title == "North Gate"
    assert snapshot.selected_summary == "Selected Door: North Gate."
    assert entity_data == before


def test_no_selection_inspector() -> None:
    inspector = build_creator_inspector(None)

    assert inspector.kind == "Thing"
    assert inspector.title == ""
    assert inspector.summary == "No object selected."
    assert inspector.fields == ()
    assert inspector.warnings == ()


def test_door_inspector_with_destination_spawn_and_trigger() -> None:
    inspector = build_creator_inspector(
        {
            "name": "North Gate",
            "behaviours": ["SceneTransition"],
            "behaviour_config": {
                "SceneTransition": {
                    "target_scene": "forest",
                    "target_spawn_id": "south_entry",
                    "listen_event": "interact",
                    "locked": False,
                }
            },
        }
    )

    assert inspector.kind == "Door"
    assert _field_value(inspector, "Destination Map") == "forest"
    assert _field_value(inspector, "Arrival Point") == "south_entry"
    assert _field_value(inspector, "Trigger") == "interact"
    assert _field_value(inspector, "Locked") == "No"
    assert inspector.warnings == ()


def test_door_inspector_warns_when_destination_missing() -> None:
    inspector = build_creator_inspector(
        {
            "behaviours": ["SceneExit"],
            "behaviour_config": {"SceneExit": {"target_spawn": "entry"}},
        }
    )

    assert inspector.kind == "Door"
    assert _field(inspector, "Destination Map").missing is True
    assert inspector.warnings == ("Door has no destination map.",)


def test_person_inspector_from_dialogue_and_quest_giver() -> None:
    inspector = build_creator_inspector(
        {
            "name": "Mayor",
            "behaviours": ["Dialogue", "QuestGiver"],
            "behaviour_config": {
                "Dialogue": {"conversation_id": "mayor_intro"},
                "QuestGiver": {"quest_id": "find_lantern"},
            },
        }
    )

    assert inspector.kind == "Person"
    assert _field_value(inspector, "Conversation") == "mayor_intro"
    assert _field_value(inspector, "Quest") == "find_lantern"


def test_monster_area_inspector_from_config() -> None:
    inspector = build_creator_inspector(
        {
            "behaviours": ["MonsterEncounterZone"],
            "behaviour_config": {
                "MonsterEncounterZone": {
                    "encounter_set": "forest_day",
                    "monster": "slime",
                    "chance": 0.25,
                    "cooldown": 8,
                }
            },
        }
    )

    assert inspector.kind == "Monster Area"
    assert _field_value(inspector, "Encounter Set") == "forest_day"
    assert _field_value(inspector, "Monster") == "slime"
    assert _field_value(inspector, "Chance") == "0.25"
    assert _field_value(inspector, "Cooldown") == "8"


def test_shopkeeper_inspector_from_vendor_config() -> None:
    inspector = build_creator_inspector(
        {
            "behaviours": ["Vendor"],
            "behaviour_config": {"Vendor": {"stock": ["potion", "ether"], "currency": "gold"}},
        }
    )

    assert inspector.kind == "Shopkeeper"
    assert _field_value(inspector, "Stock") == "potion, ether"
    assert _field_value(inspector, "Currency") == "gold"


def test_enemy_inspector_from_health_and_enemy_ai() -> None:
    inspector = build_creator_inspector(
        {
            "behaviours": ["Health", "EnemyAI"],
            "behaviour_config": {
                "Health": {"max_hp": 30},
                "EnemyAI": {"target_tag": "player"},
            },
        }
    )

    assert inspector.kind == "Enemy"
    assert _field_value(inspector, "Health") == "30"
    assert _field_value(inspector, "AI") == "EnemyAI"
    assert _field_value(inspector, "Target") == "player"


def test_light_inspector() -> None:
    inspector = build_creator_inspector(
        {
            "behaviours": ["LightSource"],
            "behaviour_config": {
                "LightSource": {
                    "light_type": "point",
                    "color": "#ffeeaa",
                    "radius": 96,
                    "intensity": 0.8,
                }
            },
        }
    )

    assert inspector.kind == "Light"
    assert _field_value(inspector, "Type") == "point"
    assert _field_value(inspector, "Color") == "#ffeeaa"
    assert _field_value(inspector, "Radius") == "96"
    assert _field_value(inspector, "Intensity") == "0.8"


def test_fallback_thing_inspector() -> None:
    inspector = build_creator_inspector({"name": "Rock", "behaviours": ["StaticSprite"]})

    assert inspector.kind == "Thing"
    assert _field_value(inspector, "Name") == "Rock"
    assert _field_value(inspector, "Behaviours") == "StaticSprite"


def test_controller_snapshot_includes_inspector() -> None:
    editor = SimpleNamespace(
        selected_entity={
            "name": "Town Door",
            "behaviour_config": {"SceneExit": {"destination": "town"}},
        }
    )
    controller = CreatorModeController(editor)

    snapshot = controller.build_snapshot()

    assert snapshot.inspector.kind == "Door"
    assert snapshot.selected_kind == snapshot.inspector.kind
    assert snapshot.selected_title == snapshot.inspector.title
    assert _field_value(snapshot.inspector, "Destination Map") == "town"


def test_build_creator_inspector_does_not_mutate_input_snapshot() -> None:
    entity_data = {
        "name": "Torch",
        "behaviours": ["LightSource"],
        "behaviour_config": {"LightSource": {"radius": 32}},
    }
    before = deepcopy(entity_data)

    build_creator_inspector(entity_data)

    assert entity_data == before


def test_overlay_model_from_inactive_snapshot() -> None:
    controller = CreatorModeController()

    overlay = build_creator_overlay_model(controller.build_snapshot())

    assert overlay.active is False
    assert overlay.title == "Creator Mode"
    assert overlay.selected_kind == "Thing"
    assert overlay.selected_summary == "No object selected."
    assert overlay.bottom_title == "Things to Fix"


def test_overlay_model_from_active_snapshot() -> None:
    controller = CreatorModeController()
    controller.show()

    overlay = build_creator_overlay_model(controller.build_snapshot())

    assert overlay.active is True
    assert overlay.title == "Creator Mode"


def test_overlay_model_includes_top_actions_and_left_tools() -> None:
    overlay = build_creator_overlay_model(CreatorModeController().build_snapshot())

    assert overlay.top_actions == ("Save", "Test Play", "Fix Problems", "Advanced Mode")
    assert overlay.left_tools == (
        "Map",
        "Person",
        "Door",
        "Monster Area",
        "Battle",
        "Quest",
        "Item",
        "Light",
    )


def test_overlay_model_includes_inspector_fields() -> None:
    controller = CreatorModeController(
        SimpleNamespace(
            selected_entity={
                "name": "North Gate",
                "behaviour_config": {"SceneExit": {"target_scene": "town"}},
            }
        )
    )

    overlay = build_creator_overlay_model(controller.build_snapshot())

    assert ("Destination Map", "town", False) in overlay.inspector_fields


def test_overlay_model_includes_warnings() -> None:
    controller = CreatorModeController(
        SimpleNamespace(
            selected_entity={
                "behaviours": ["SceneExit"],
                "behaviour_config": {"SceneExit": {"target_spawn": "entry"}},
            }
        )
    )

    overlay = build_creator_overlay_model(controller.build_snapshot())

    assert overlay.warnings == ("Door has no destination map.",)


def test_inactive_overlay_renderer_path_produces_no_draw_commands() -> None:
    model = build_creator_overlay_model(CreatorModeController().build_snapshot())

    commands = build_creator_overlay_draw_commands(model, 1280, 720)

    assert commands == ()


def test_active_overlay_draw_commands_include_shell_content() -> None:
    controller = CreatorModeController()
    controller.show()
    model = build_creator_overlay_model(controller.build_snapshot())

    commands = build_creator_overlay_draw_commands(model, 1280, 720)
    text = _command_text(commands)

    assert "Creator Mode" in text
    assert "Read-only preview" in text
    assert "Save | Test Play | Fix Problems | Advanced Mode" in text
    assert "Map" in text
    assert "Light" in text
    assert "Things to Fix" in text


def test_active_overlay_draw_commands_include_inspector_fields() -> None:
    controller = CreatorModeController(
        SimpleNamespace(
            selected_entity={
                "name": "North Gate",
                "behaviour_config": {"SceneExit": {"target_scene": "town"}},
            }
        )
    )
    controller.show()
    model = build_creator_overlay_model(controller.build_snapshot())

    commands = build_creator_overlay_draw_commands(model, 1280, 720)
    text = _command_text(commands)

    assert "Door" in text
    assert "North Gate" in text
    assert "Destination Map: town" in text


def test_active_overlay_draw_commands_include_warning_text() -> None:
    controller = CreatorModeController(
        SimpleNamespace(
            selected_entity={
                "behaviours": ["SceneExit"],
                "behaviour_config": {"SceneExit": {"target_spawn": "entry"}},
            }
        )
    )
    controller.show()
    model = build_creator_overlay_model(controller.build_snapshot())

    commands = build_creator_overlay_draw_commands(model, 1280, 720)
    text = _command_text(commands)

    assert "Door has no destination map." in text


def test_overlay_draw_command_build_does_not_mutate_input_snapshot() -> None:
    entity_data = {
        "name": "Torch",
        "behaviours": ["LightSource"],
        "behaviour_config": {"LightSource": {"radius": 32}},
    }
    before = deepcopy(entity_data)
    controller = CreatorModeController(SimpleNamespace(selected_entity=entity_data))
    controller.show()

    model = build_creator_overlay_model(controller.build_snapshot())
    build_creator_overlay_draw_commands(model, 1280, 720)

    assert entity_data == before


def test_long_selected_title_is_truncated_in_draw_commands() -> None:
    long_title = "North Gate " * 12
    controller = CreatorModeController(
        SimpleNamespace(
            selected_entity={
                "name": long_title,
                "behaviour_config": {"SceneExit": {"target_scene": "town"}},
            }
        )
    )
    controller.show()

    commands = build_creator_overlay_draw_commands(
        build_creator_overlay_model(controller.build_snapshot()),
        1280,
        720,
    )
    text = _command_text(commands)

    assert long_title.strip() not in text
    assert truncate_creator_overlay_text(long_title, 42) in text


def test_long_inspector_value_is_truncated_in_draw_commands() -> None:
    long_destination = "very_long_destination_map_" * 8
    controller = CreatorModeController(
        SimpleNamespace(
            selected_entity={
                "name": "North Gate",
                "behaviour_config": {"SceneExit": {"target_scene": long_destination}},
            }
        )
    )
    controller.show()

    commands = build_creator_overlay_draw_commands(
        build_creator_overlay_model(controller.build_snapshot()),
        1280,
        720,
    )
    text = _command_text(commands)

    assert f"Destination Map: {long_destination}" not in text
    assert "Destination Map: very_long_destination_map_" in text
    assert "..." in text


def test_very_small_window_produces_sane_overlay_commands() -> None:
    controller = CreatorModeController()
    controller.show()
    model = build_creator_overlay_model(controller.build_snapshot())

    commands = build_creator_overlay_draw_commands(model, 220, 140)

    rects = [command for command in commands if command.kind == "rect"]
    assert rects
    assert all(command.width > 0 for command in rects)
    assert all(command.height > 0 for command in rects)
    assert all(command.x >= 0 for command in commands)
    assert all(command.y >= 0 for command in commands)
    assert "Read-only preview" in _command_text(commands)


def test_missing_inspector_fields_are_distinct_in_draw_command_data() -> None:
    controller = CreatorModeController(
        SimpleNamespace(
            selected_entity={
                "behaviours": ["SceneExit"],
                "behaviour_config": {"SceneExit": {"target_spawn": "entry"}},
            }
        )
    )
    controller.show()

    commands = build_creator_overlay_draw_commands(
        build_creator_overlay_model(controller.build_snapshot()),
        1280,
        720,
    )

    assert any(
        command.kind == "text"
        and command.region == "right"
        and command.missing
        and command.text.startswith("Destination Map:")
        for command in commands
    )


def test_draw_creator_overlay_without_snapshot_method_does_not_raise() -> None:
    draw_creator_overlay(SimpleNamespace())


def test_draw_creator_overlay_with_bad_snapshot_data_does_not_raise() -> None:
    bad_editor = SimpleNamespace(
        creator_mode_snapshot=lambda: SimpleNamespace(active=True),
        window=SimpleNamespace(width=1280, height=720),
    )

    draw_creator_overlay(bad_editor)


def test_draw_creator_overlay_with_draw_failure_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    controller = CreatorModeController()
    controller.show()
    editor = SimpleNamespace(
        creator_mode_snapshot=controller.build_snapshot,
        window=SimpleNamespace(width=1280, height=720),
    )

    def fail_draw(*_args, **_kwargs) -> None:
        raise RuntimeError("draw failed")

    monkeypatch.setattr(creator_overlay_renderer, "_draw_rectangle_filled", fail_draw)

    draw_creator_overlay(editor)


def test_editor_integration_owns_creator_mode_controller_without_mutating_scene_data() -> None:
    window = _MockWindow()
    entity_data = {
        "name": "Town Door",
        "behaviour_config": {"SceneExit": {"destination": "town"}},
    }
    before = deepcopy(entity_data)
    editor = EditorModeController(window)
    editor.selected_entity = SimpleNamespace(mesh_entity_data=entity_data)

    snapshot = editor.creator_mode_snapshot()

    assert isinstance(editor.creator_mode, CreatorModeController)
    assert snapshot.selected_kind == "Door"
    assert entity_data == before


def test_editor_toggle_creator_mode_flips_active_state() -> None:
    editor = EditorModeController(_MockWindow())

    assert editor.creator_mode.active is False
    assert editor.toggle_creator_mode() is True
    assert editor.creator_mode.active is True
    assert editor.toggle_creator_mode() is False


def test_editor_shift_f5_toggles_creator_mode_when_editor_active() -> None:
    editor = EditorModeController(_MockWindow())
    editor.active = True

    consumed = editor.handle_input(
        optional_arcade.arcade.key.F5,
        optional_arcade.arcade.key.MOD_SHIFT,
    )

    assert consumed is True
    assert editor.creator_mode.active is True


def test_editor_plain_f5_does_not_toggle_creator_mode_when_editor_active() -> None:
    editor = EditorModeController(_MockWindow())
    editor.active = True

    consumed = editor.handle_input(optional_arcade.arcade.key.F5, 0)

    assert consumed is False
    assert editor.creator_mode.active is False


def test_editor_shift_f5_does_not_toggle_creator_mode_when_editor_inactive() -> None:
    editor = EditorModeController(_MockWindow())

    consumed = editor.handle_input(
        optional_arcade.arcade.key.F5,
        optional_arcade.arcade.key.MOD_SHIFT,
    )

    assert consumed is False
    assert editor.creator_mode.active is False


def test_editor_shift_f5_toggles_creator_mode_with_lock_key_modifiers() -> None:
    editor = EditorModeController(_MockWindow())
    editor.active = True
    caps = int(getattr(optional_arcade.arcade.key, "MOD_CAPSLOCK", 0) or 0)

    consumed = editor.handle_input(
        optional_arcade.arcade.key.F5,
        optional_arcade.arcade.key.MOD_SHIFT | caps,
    )

    assert consumed is True
    assert editor.creator_mode.active is True


def test_input_dispatch_shift_f5_toggles_creator_mode_when_editor_active() -> None:
    window = _DispatchWindow()
    window.editor_controller.toggle()

    input_dispatch.on_key_press(
        window,
        optional_arcade.arcade.key.F5,
        optional_arcade.arcade.key.MOD_SHIFT,
    )

    assert window.editor_controller.creator_mode.active is True
    window.input_controller.on_key_press.assert_not_called()


def test_input_dispatch_shift_f5_with_caps_lock_toggles_creator_mode_when_editor_active() -> None:
    window = _DispatchWindow()
    window.editor_controller.toggle()
    caps = int(getattr(optional_arcade.arcade.key, "MOD_CAPSLOCK", 0) or 0)

    input_dispatch.on_key_press(
        window,
        optional_arcade.arcade.key.F5,
        optional_arcade.arcade.key.MOD_SHIFT | caps,
    )

    assert window.editor_controller.creator_mode.active is True


def test_friendly_engine_terms() -> None:
    assert friendly_engine_term("Entity") == "Thing"
    assert friendly_engine_term("Behaviour") == "What it does"
    assert friendly_engine_term("Scene") == "Map"
    assert friendly_engine_term("SceneExit") == "Door"
    assert friendly_engine_term("SceneTransition") == "Door"
    assert friendly_engine_term("TriggerZone") == "Area"
    assert friendly_engine_term("MonsterEncounterZone") == "Monster Area"
    assert friendly_engine_term("Vendor") == "Shopkeeper"


def test_door_classification_from_behaviour_names_and_config() -> None:
    assert classify_entity_snapshot({"behaviours": ["SceneTransition"]}) == "Door"
    assert classify_entity_snapshot({"behaviour_config": {"SceneExit": {"target": "field"}}}) == "Door"


def test_monster_area_classification() -> None:
    assert classify_entity_snapshot({"behaviours": ["MonsterEncounterZone"]}) == "Monster Area"


def test_shopkeeper_classification() -> None:
    assert classify_entity_snapshot({"behaviours": ["Vendor"]}) == "Shopkeeper"
    assert classify_entity_snapshot({"behaviour_config": {"Vendor": {"stock": []}}}) == "Shopkeeper"


def test_enemy_classification() -> None:
    entity = {"behaviours": ["Health", "EnemyAI"]}

    assert classify_entity_snapshot(entity) == "Enemy"


def test_light_classification() -> None:
    assert classify_entity_snapshot({"behaviours": ["LightSource"]}) == "Light"
    assert classify_entity_snapshot({"name": "Blue Light"}) == "Light"


def test_fallback_classification_is_thing() -> None:
    assert classify_entity_snapshot({"name": "Rock"}) == "Thing"
    assert classify_entity_snapshot(None) == "Thing"


def _field(inspector, label: str):
    return next(field for field in inspector.fields if field.label == label)


def _field_value(inspector, label: str) -> str:
    return _field(inspector, label).value


def _command_text(commands) -> str:
    return "\n".join(command.text for command in commands if command.kind == "text")


class _MockWindow:
    def __init__(self) -> None:
        cfg = EngineConfig()
        self.width = cfg.width
        self.height = cfg.height
        self.paused = False
        self.scene_controller = MagicMock()
        self.screen_to_world = MagicMock(return_value=(100, 100))


class _DispatchWindow(_MockWindow):
    def __init__(self) -> None:
        super().__init__()
        self.game_over = False
        self.engine_config = EngineConfig()
        self.console_controller = MagicMock(active=False)
        self.ui_controller = MagicMock(on_key_press=lambda *_args: False)
        self.settings_overlay = MagicMock()
        self.input_controller = MagicMock(on_key_press=MagicMock())
        self.pause_menu = MagicMock(visible=False)
        self.console_log = lambda _message: None
        self.editor_controller = EditorModeController(self)
        self.editor_controller.window = self
