import arcade

from engine.config import EngineConfig
from engine.editor_controller import EditorModeController


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


def make_anim_sprite():
    sprite = type("DummySprite", (), {})()
    sprite.mesh_name = "Animated"
    sprite.mesh_behaviours = ["Animator"]
    sprite.mesh_behaviours_runtime = []
    sprite.mesh_entity_data = {
        "name": "Animated",
        "behaviour_config": {
            "Animator": {
                "animations": {
                    "idle": {"frames": ["frame0.png", "frame1.png"], "fps": 8.0, "mode": "loop"}
                }
            }
        },
    }
    sprite.layer = "entities"
    sprite.width = 16
    sprite.height = 16
    sprite.center_x = 0
    sprite.center_y = 0
    return sprite


def test_animation_panel_open_and_edit():
    sprite = make_anim_sprite()
    window = DummyWindow(sprite)
    controller = EditorModeController(window)
    controller.active = True
    controller.selected_entity = sprite

    controller.toggle_animation_panel()
    assert controller.animation_active

    controller.animation_field_focus = "fps"
    controller.handle_input(arcade.key.RIGHT, 0)
    anim_cfg = sprite.mesh_entity_data["behaviour_config"]["Animator"]["animations"]["idle"]
    assert anim_cfg["fps"] > 8.0

    controller.undo_last()
    anim_cfg = sprite.mesh_entity_data["behaviour_config"]["Animator"]["animations"]["idle"]
    assert anim_cfg["fps"] == 8.0

    controller.redo_last()
    anim_cfg = sprite.mesh_entity_data["behaviour_config"]["Animator"]["animations"]["idle"]
    assert anim_cfg["fps"] > 8.0


def test_animation_panel_ignores_entities_without_animator():
    sprite = make_anim_sprite()
    sprite.mesh_behaviours = []
    window = DummyWindow(sprite)
    controller = EditorModeController(window)
    controller.active = True
    controller.selected_entity = sprite
    controller.toggle_animation_panel()
    assert controller.animation_active is False
