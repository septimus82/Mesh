import types
from unittest.mock import MagicMock

import engine.optional_arcade as optional_arcade

from engine.scene_index import SceneIndex
from engine.ui import DevBrowserOverlay
from tests._typing import as_any


class StubSprite:
    def __init__(self, *, entity_data: dict | None = None, mesh_name: str | None = None) -> None:
        self.mesh_entity_data = entity_data
        self.mesh_name = mesh_name


def _make_window_with_sprites(sprites: list[StubSprite]):
    window = types.SimpleNamespace()
    window.width = 800
    window.height = 600
    window.player_hud = types.SimpleNamespace(enqueue_toast=MagicMock())
    window.set_next_spawn_point = MagicMock()
    window.request_reload_current_scene = MagicMock()
    window.request_scene_change = MagicMock()

    idx = SceneIndex.build_from_sprites(sprites)

    controller = types.SimpleNamespace()
    controller.current_scene_path = "packs/core_regions/scenes/Ridge Outpost_hub.json"
    controller.all_sprites = sprites
    controller._ensure_scene_index = lambda: idx
    window.scene_controller = controller

    return window


def test_l_only_works_in_jump_mode_in_scenes_tab() -> None:
    window = _make_window_with_sprites([])
    overlay = DevBrowserOverlay(as_any(window))
    overlay.visible = True

    overlay.mode = "scenes"
    overlay.jump_mode = False
    overlay.on_key_press(optional_arcade.arcade.key.L, 0)
    assert overlay.jump_list_open is False

    overlay.mode = "worlds"
    overlay.jump_mode = True
    overlay.on_key_press(optional_arcade.arcade.key.L, 0)
    assert overlay.jump_list_open is False

    overlay.mode = "scenes"
    overlay.jump_mode = True
    overlay.on_key_press(optional_arcade.arcade.key.L, 0)
    assert overlay.jump_list_open is True


def test_jump_list_build_order_and_first_wins_is_deterministic() -> None:
    sprites = [
        StubSprite(entity_data={"id": "Alpha"}, mesh_name="MeshAlpha"),
        StubSprite(entity_data={"id": "Alpha"}, mesh_name="MeshDupId"),
        StubSprite(entity_data={"behaviour_config": {"TriggerZone": {"zone_id": "Zone1"}}}, mesh_name="ZoneMesh"),
        StubSprite(entity_data={"behaviour_config": {"TriggerZone": {"zone_id": "Zone1"}}}, mesh_name="ZoneDup"),
        StubSprite(entity_data={}, mesh_name="MeshOnly"),
        StubSprite(entity_data={}, mesh_name="MeshOnly"),
        StubSprite(entity_data={"id": "IdOnly"}, mesh_name=None),
    ]
    window = _make_window_with_sprites(sprites)
    overlay = DevBrowserOverlay(as_any(window))
    overlay.visible = True
    overlay.mode = "scenes"

    overlay.on_key_press(optional_arcade.arcade.key.SLASH, 0)
    overlay.on_key_press(optional_arcade.arcade.key.L, 0)

    assert overlay.jump_list_open is True
    assert [i["spawn_key"] for i in overlay.jump_list_items] == ["alpha", "idonly", "zone1", "meshonly"]


def test_jump_list_up_down_clamps() -> None:
    sprites = [
        StubSprite(entity_data={"id": "a"}, mesh_name=None),
        StubSprite(entity_data={"id": "b"}, mesh_name=None),
        StubSprite(entity_data={"id": "c"}, mesh_name=None),
    ]
    window = _make_window_with_sprites(sprites)
    overlay = DevBrowserOverlay(as_any(window))
    overlay.visible = True
    overlay.mode = "scenes"

    overlay.on_key_press(optional_arcade.arcade.key.SLASH, 0)
    overlay.on_key_press(optional_arcade.arcade.key.L, 0)
    assert overlay.jump_list_index == 0

    overlay.on_key_press(optional_arcade.arcade.key.UP, 0)
    assert overlay.jump_list_index == 0

    overlay.on_key_press(optional_arcade.arcade.key.DOWN, 0)
    overlay.on_key_press(optional_arcade.arcade.key.DOWN, 0)
    overlay.on_key_press(optional_arcade.arcade.key.DOWN, 0)
    assert overlay.jump_list_index == 2


def test_enter_with_list_open_jumps_and_closes_jump_mode_after_success() -> None:
    sprites = [
        StubSprite(entity_data={"id": "Alpha"}, mesh_name="MeshAlpha"),
        StubSprite(entity_data={"behaviour_config": {"TriggerZone": {"zone_id": "Zone1"}}}, mesh_name=None),
    ]
    window = _make_window_with_sprites(sprites)
    overlay = DevBrowserOverlay(as_any(window))
    overlay.visible = True
    overlay.mode = "scenes"

    overlay.on_key_press(optional_arcade.arcade.key.SLASH, 0)
    overlay.on_key_press(optional_arcade.arcade.key.L, 0)
    assert overlay.jump_list_open is True

    overlay.jump_list_index = 1
    overlay.on_key_press(optional_arcade.arcade.key.ENTER, 0)

    window.set_next_spawn_point.assert_called_once_with("zone1")
    window.request_reload_current_scene.assert_called_once_with()
    window.request_scene_change.assert_not_called()
    window.player_hud.enqueue_toast.assert_called_once()
    assert window.player_hud.enqueue_toast.call_args.args[0] == "Jumped to: zone1"

    assert overlay.visible is True
    assert overlay.jump_mode is False
    assert overlay.jump_list_open is False


def test_esc_closes_list_first_then_exits_jump_mode() -> None:
    sprites = [StubSprite(entity_data={"id": "Alpha"}, mesh_name=None)]
    window = _make_window_with_sprites(sprites)
    overlay = DevBrowserOverlay(as_any(window))
    overlay.visible = True
    overlay.mode = "scenes"

    overlay.on_key_press(optional_arcade.arcade.key.SLASH, 0)
    overlay.on_key_press(optional_arcade.arcade.key.L, 0)
    assert overlay.jump_list_open is True
    assert overlay.jump_mode is True

    overlay.on_key_press(optional_arcade.arcade.key.ESCAPE, 0)
    assert overlay.jump_list_open is False
    assert overlay.jump_mode is True

    overlay.on_key_press(optional_arcade.arcade.key.ESCAPE, 0)
    assert overlay.jump_mode is False
    assert overlay.visible is True


def test_typing_in_jump_mode_does_not_move_list_selection() -> None:
    sprites = [
        StubSprite(entity_data={"id": "a"}, mesh_name=None),
        StubSprite(entity_data={"id": "b"}, mesh_name=None),
        StubSprite(entity_data={"id": "c"}, mesh_name=None),
    ]
    window = _make_window_with_sprites(sprites)
    overlay = DevBrowserOverlay(as_any(window))
    overlay.visible = True
    overlay.mode = "scenes"

    overlay.on_key_press(optional_arcade.arcade.key.SLASH, 0)
    overlay.on_key_press(optional_arcade.arcade.key.L, 0)
    overlay.jump_list_index = 2

    overlay.on_text("x")
    assert overlay.jump_list_index == 2
    assert overlay.jump_text == "x"

