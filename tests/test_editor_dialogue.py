import arcade
import pytest

from engine.editor_controller import EditorModeController
from engine.config import EngineConfig


class DummySceneController:
    def __init__(self, sprite):
        self._sprite = sprite

    @property
    def all_sprites(self):
        return [self._sprite]

    def _ensure_entity_data_dict(self, sprite):
        if not hasattr(sprite, "mesh_entity_data") or sprite.mesh_entity_data is None:
            sprite.mesh_entity_data = {}
        return sprite.mesh_entity_data

    def _ensure_behaviour_config_root(self, entity_data):
        return entity_data.setdefault("behaviour_config", {})

    def _get_behaviour_configs_for_sprite(self, sprite):
        entity_data = self._ensure_entity_data_dict(sprite)
        cfg_root = self._ensure_behaviour_config_root(entity_data)
        result = []
        for behaviour_name, params in cfg_root.items():
            if isinstance(params, dict):
                result.append({"type": behaviour_name, "params": dict(params)})
        return result

    def _apply_entity_mutation(self, sprite, **kwargs):
        entity_data = self._ensure_entity_data_dict(sprite)
        entity_data.update(kwargs)

    def add_sprite_to_layer(self, sprite, layer):
        return


class DummyWindow:
    def __init__(self, sprite):
        cfg = EngineConfig()
        self.width = cfg.width
        self.height = cfg.height
        self.paused = False
        self.scene_controller = DummySceneController(sprite)
        self.screen_to_world = lambda x, y: (x, y)
        self.quest_manager = None


def make_dialogue_sprite():
    sprite = type("DummySprite", (), {})()
    sprite.mesh_name = "NPC"
    sprite.mesh_behaviours = ["Dialogue"]
    sprite.mesh_entity_data = {
        "name": "NPC",
        "behaviour_config": {
            "Dialogue": {
                "dialogue": {
                    "start": "intro",
                    "nodes": {
                        "intro": {
                            "text": "Hello there",
                            "choices": [
                                {"id": "c1", "text": "Hi", "next": None},
                            ],
                        }
                    },
                }
            }
        },
    }
    sprite.mesh_behaviours_runtime = []
    sprite.layer = "entities"
    sprite.width = 16
    sprite.height = 16
    sprite.center_x = 0
    sprite.center_y = 0
    return sprite


def test_dialogue_edit_and_undo_redo():
    sprite = make_dialogue_sprite()
    window = DummyWindow(sprite)
    controller = EditorModeController(window)
    controller.active = True
    controller.selected_entity = sprite

    controller.toggle_dialogue_panel()
    assert controller.dialogue_panel_active

    controller.dialogue_selected_node = 0
    controller.dialogue_selected_choice = 0
    controller.dialogue_field_focus = "choice_text"

    controller.handle_input(arcade.key.ENTER, 0)
    controller.dialogue_edit_buffer = "Updated greeting"
    controller.handle_input(arcade.key.ENTER, 0)

    dialogue_cfg = sprite.mesh_entity_data["behaviour_config"]["Dialogue"]["dialogue"]
    assert dialogue_cfg["nodes"]["intro"]["choices"][0]["text"] == "Updated greeting"

    controller.undo_last()
    dialogue_cfg = sprite.mesh_entity_data["behaviour_config"]["Dialogue"]["dialogue"]
    assert dialogue_cfg["nodes"]["intro"]["choices"][0]["text"] == "Hi"

    controller.redo_last()
    dialogue_cfg = sprite.mesh_entity_data["behaviour_config"]["Dialogue"]["dialogue"]
    assert dialogue_cfg["nodes"]["intro"]["choices"][0]["text"] == "Updated greeting"


def test_related_quests_highlight():
    sprite = make_dialogue_sprite()
    sprite.mesh_entity_data["behaviour_config"]["QuestProgressOnEvent"] = {"quest_id": "quest_alpha"}
    sprite.mesh_behaviours.append("QuestProgressOnEvent")
    window = DummyWindow(sprite)
    window.quest_manager = type("QM", (), {"_definitions": {"quest_alpha": {"id": "quest_alpha", "stages": []}}})()
    controller = EditorModeController(window)
    controller.active = True
    controller.selected_entity = sprite
    related = controller._related_quest_ids(sprite)
    assert "quest_alpha" in related
