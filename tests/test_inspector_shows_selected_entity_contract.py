from __future__ import annotations

from typing import Any

import pytest

import engine.editor_controller as editor_module
import engine.optional_arcade as optional_arcade
from engine.editor_controller import EditorModeController
from engine.ui_overlays.component_inspector_overlay import ComponentInspectorOverlay
from tests._editor_window_stub import EditorWindowStub, as_game_window

pytestmark = [pytest.mark.fast]


class _Sprite:
    def __init__(self, entity_id: str) -> None:
        self.mesh_name = entity_id
        self.mesh_tag = "entity"
        self.mesh_behaviours: list[Any] = []
        self.mesh_behaviours_runtime: list[Any] = []
        self.mesh_entity_data: dict[str, Any] = {
            "id": entity_id,
            "name": "Player",
            "x": 400.0,
            "y": 300.0,
            "sprite": "player.png",
            "behaviours": ["Interactable"],
            "behaviour_config": {},
        }
        self.center_x = 400.0
        self.center_y = 300.0
        self.width = 32
        self.height = 32
        self.angle = 0.0

    def collides_with_point(self, _point: tuple[float, float]) -> bool:
        return True


class _SceneController:
    def __init__(self, sprite: _Sprite) -> None:
        self.all_sprites = [sprite]
        self.entity_sprites = [sprite]
        self.layers = {"entities": [sprite]}
        self.solid_sprites: list[_Sprite] = []
        self.tilemap_instance = None
        self.current_scene_path = "scenes/test_scene.json"
        self._loaded_scene_data = {"entities": [sprite.mesh_entity_data]}

    def get_sprites_in_layer(self, layer_name: str) -> list[_Sprite] | None:
        return self.layers.get(layer_name)

    def _ensure_entity_data_dict(self, sprite: _Sprite) -> dict[str, Any]:
        return sprite.mesh_entity_data

    def _ensure_behaviour_config_root(self, entity_data: dict[str, Any]) -> dict[str, Any]:
        root = entity_data.get("behaviour_config")
        if not isinstance(root, dict):
            root = {}
            entity_data["behaviour_config"] = root
        return root

    def _apply_entity_mutation(self, sprite: _Sprite, *, x: float | None = None, y: float | None = None, **_kwargs: Any) -> None:
        if x is not None:
            sprite.center_x = float(x)
            sprite.mesh_entity_data["x"] = float(x)
        if y is not None:
            sprite.center_y = float(y)
            sprite.mesh_entity_data["y"] = float(y)

    def build_scene_snapshot(self) -> dict[str, Any]:
        return {}


def _make_controller(monkeypatch: pytest.MonkeyPatch) -> tuple[EditorModeController, EditorWindowStub, _Sprite]:
    monkeypatch.setattr(editor_module, "PREFAB_PALETTE", [])
    monkeypatch.setattr(editor_module, "load_prefab_palette", lambda *args, **kwargs: [])

    sprite = _Sprite("player")
    scene = _SceneController(sprite)
    window = EditorWindowStub(scene_controller=scene, width=800, height=600)
    controller = EditorModeController(as_game_window(window))
    setattr(window, "editor_controller", controller)
    controller.toggle()
    return controller, window, sprite


def test_inspector_getter_returns_viewport_selected_entity_json(monkeypatch: pytest.MonkeyPatch) -> None:
    controller, _window, sprite = _make_controller(monkeypatch)

    assert controller.handle_mouse_click(400, 300, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True

    entity_json = controller._get_selected_entity_json_for_inspector()

    assert entity_json is sprite.mesh_entity_data
    assert entity_json["sprite"] == "player.png"
    assert entity_json["behaviours"] == ["Interactable"]
    assert entity_json["x"] == 400.0
    assert entity_json["y"] == 300.0


def test_component_inspector_overlay_uses_selected_entity_json(monkeypatch: pytest.MonkeyPatch) -> None:
    controller, window, sprite = _make_controller(monkeypatch)
    overlay = ComponentInspectorOverlay(as_game_window(window))
    drew_sections: list[bool] = []
    drew_no_selection: list[bool] = []

    monkeypatch.setattr(overlay, "_draw_sections", lambda *args, **kwargs: drew_sections.append(True))
    monkeypatch.setattr(overlay, "_draw_no_selection", lambda: drew_no_selection.append(True))

    assert controller.handle_mouse_click(400, 300, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True

    entity_json = overlay._get_selected_entity_json(controller)
    overlay.draw()

    assert entity_json is sprite.mesh_entity_data
    assert drew_sections == [True]
    assert drew_no_selection == []
