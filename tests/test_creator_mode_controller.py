from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from engine.editor.creator_mode import CreatorModeController
from engine.editor.creator_mode.creator_terms import classify_entity_snapshot, friendly_engine_term

pytestmark = pytest.mark.fast


def test_controller_starts_inactive() -> None:
    controller = CreatorModeController()

    assert controller.active is False
    assert controller.build_snapshot().active is False


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
