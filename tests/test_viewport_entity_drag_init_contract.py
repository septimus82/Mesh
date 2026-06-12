from __future__ import annotations

from typing import Any

import pytest

import engine.editor_controller as editor_module
import engine.optional_arcade as optional_arcade
from engine.editor.state import TRANSFORM_MODE_ROTATE
from engine.editor_controller import EditorModeController
from tests._editor_window_stub import EditorWindowStub, as_game_window

pytestmark = [pytest.mark.fast]


class _Sprite:
    def __init__(self, entity_id: str, *, collides: bool = True) -> None:
        self.mesh_name = entity_id
        self.mesh_tag = "entity"
        self.mesh_behaviours: list[Any] = []
        self.mesh_behaviours_runtime: list[Any] = []
        self.mesh_entity_data: dict[str, Any] = {
            "id": entity_id,
            "name": entity_id,
            "x": 400.0,
            "y": 300.0,
            "behaviour_config": {},
        }
        self.center_x = 400.0
        self.center_y = 300.0
        self.width = 32
        self.height = 32
        self.angle = 0.0
        self._collides = collides
        self.collide_calls = 0

    def collides_with_point(self, _point: tuple[float, float]) -> bool:
        self.collide_calls += 1
        return self._collides


class _SceneController:
    def __init__(
        self,
        sprites: list[_Sprite],
        *,
        all_sprites: list[_Sprite] | None = None,
        entity_sprites: list[_Sprite] | None = None,
        layers: dict[str, list[_Sprite]] | None = None,
    ) -> None:
        self._sprites = sprites if all_sprites is None else all_sprites
        self.entity_sprites = sprites if entity_sprites is None else entity_sprites
        self.layers = {"entities": sprites} if layers is None else layers
        self.solid_sprites: list[_Sprite] = []
        self.tilemap_instance = None
        self.current_scene_path = "scenes/test_scene.json"

    @property
    def all_sprites(self) -> list[_Sprite]:
        return self._sprites

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


@pytest.fixture
def editor_controller(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(editor_module, "PREFAB_PALETTE", [])
    monkeypatch.setattr(editor_module, "load_prefab_palette", lambda *args, **kwargs: [])

    def make(sprites: list[_Sprite]) -> EditorModeController:
        return _controller_for_scene(_SceneController(sprites))

    return make


def _controller_for_scene(scene: _SceneController) -> EditorModeController:
    window = EditorWindowStub(scene_controller=scene, width=800, height=600)
    controller = EditorModeController(as_game_window(window))
    controller.toggle()
    return controller


def test_plain_move_click_on_unselected_entity_prepares_drag(editor_controller) -> None:
    sprite = _Sprite("entity-a")
    controller = editor_controller([sprite])

    assert controller._selected_entity_ids == []
    assert controller.handle_mouse_click(400, 300, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True

    assert controller.selected_entity is sprite
    assert controller._selected_entity_ids == ["entity-a"]
    assert controller.entity_dragging is True
    assert controller.entity_drag_start_pos == (400.0, 300.0)


def test_shift_click_on_entity_toggles_selection_without_preparing_drag(editor_controller) -> None:
    sprite = _Sprite("entity-a")
    controller = editor_controller([sprite])

    assert (
        controller.handle_mouse_click(
            400,
            300,
            optional_arcade.arcade.MOUSE_BUTTON_LEFT,
            optional_arcade.arcade.key.MOD_SHIFT,
        )
        is True
    )

    assert controller.selected_entity is sprite
    assert controller._selected_entity_ids == ["entity-a"]
    assert controller.entity_dragging is False
    assert controller.entity_drag_start_pos is None


def test_path_tool_entity_click_does_not_prepare_drag(editor_controller) -> None:
    sprite = _Sprite("entity-a")
    controller = editor_controller([sprite])
    controller.tool_mode = "PATH"

    assert controller.handle_mouse_click(400, 300, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True

    assert controller.selected_entity is sprite
    assert controller.entity_dragging is False
    assert controller.entity_drag_start_pos is None


def test_move_tool_rotate_transform_click_prepares_rotate_drag(editor_controller) -> None:
    sprite = _Sprite("entity-a")
    controller = editor_controller([sprite])
    controller.transform_mode = TRANSFORM_MODE_ROTATE

    assert controller.handle_mouse_click(400, 300, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True

    assert controller.selected_entity is sprite
    assert controller.entity_dragging is False
    assert controller._rotate_drag_active is True
    assert controller._transform_drag_pivot == (400.0, 300.0)


def test_empty_viewport_click_starts_marquee_not_drag(editor_controller) -> None:
    controller = editor_controller([])

    assert controller.handle_mouse_click(400, 300, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True

    assert controller.selected_entity is None
    assert controller.entity_dragging is False
    assert controller._marquee_active is True
    assert controller._marquee_start_world == (400.0, 300.0)


def test_entity_sprites_source_hit_prepares_drag_when_all_sprites_is_empty() -> None:
    sprite = _Sprite("entity-a")
    scene = _SceneController([], all_sprites=[], entity_sprites=[sprite], layers={})
    controller = _controller_for_scene(scene)

    assert controller.handle_mouse_click(400, 300, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True

    assert controller.selected_entity is sprite
    assert controller.entity_dragging is True
    assert controller.entity_drag_start_pos == (400.0, 300.0)


def test_picker_dedupes_multiple_sources_and_selects_topmost_layer_sprite() -> None:
    bottom = _Sprite("entity-bottom")
    top = _Sprite("entity-top")
    sprites = [bottom, top]
    scene = _SceneController(sprites, all_sprites=sprites, entity_sprites=sprites, layers={"entities": sprites})
    controller = _controller_for_scene(scene)

    assert controller.handle_mouse_click(400, 300, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True

    assert controller.selected_entity is top
    assert controller._selected_entity_ids == ["entity-top"]
    assert bottom.collide_calls == 1
    assert top.collide_calls == 1


def test_picker_accepts_rendered_bounds_when_sprite_hitbox_misses() -> None:
    sprite = _Sprite("entity-a", collides=False)
    controller = _controller_for_scene(_SceneController([sprite]))

    assert controller.handle_mouse_click(400, 300, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True

    assert controller.selected_entity is sprite
    assert controller.entity_dragging is True
    assert sprite.collide_calls == 1


def test_bounds_fallback_preserves_topmost_ordering() -> None:
    bottom = _Sprite("entity-bottom", collides=False)
    top = _Sprite("entity-top", collides=False)
    controller = _controller_for_scene(_SceneController([bottom, top]))

    assert controller.handle_mouse_click(400, 300, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True

    assert controller.selected_entity is top
    assert controller._selected_entity_ids == ["entity-top"]


def test_empty_position_across_all_sprite_sources_starts_marquee_not_drag() -> None:
    miss = _Sprite("entity-a", collides=False)
    scene = _SceneController([miss], all_sprites=[miss], entity_sprites=[miss], layers={"entities": [miss]})
    controller = _controller_for_scene(scene)

    assert controller.handle_mouse_click(500, 300, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True

    assert controller.selected_entity is None
    assert controller.entity_dragging is False
    assert controller._marquee_active is True
    assert miss.collide_calls == 1


def test_viewport_rendered_entity_in_layer_drags_without_outliner_selection() -> None:
    sprite = _Sprite("player")
    scene = _SceneController([], all_sprites=[], entity_sprites=[], layers={"entities": [sprite]})
    controller = _controller_for_scene(scene)

    assert controller._selected_entity_ids == []
    assert controller.handle_mouse_click(400, 300, optional_arcade.arcade.MOUSE_BUTTON_LEFT, 0) is True

    assert controller.selected_entity is sprite
    assert controller._selected_entity_ids == ["player"]
    assert controller.entity_dragging is True
